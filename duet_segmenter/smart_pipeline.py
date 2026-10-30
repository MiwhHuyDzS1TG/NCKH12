"""Profile-based dual-domain P1.4 pipeline and Smart AUTO audio path."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .alignment import align, build_aligned_reference
from .audibility import contamination_scope, measure_reference_presence
from .cancellation import cancel_reference
from .leakage import diagnose
from .media import SAMPLE_RATE, normalize_audio, write_wav
from .pipeline import _write_json
from .profile import TemplateProfile
from .quality import background_interference, low_speech_level, measure_audio_quality
from .scorability import decide_scorability
from .segments import classify, clip_segments, overlap_intersections
from .vad import SileroDetector, mean_probability
from .visual import align_video


def _mapped_vad(vad: list[dict], a: float, b: float, duration: float) -> list[dict]:
    return clip_segments([{"start": a*x["start"]+b, "end": a*x["end"]+b}
                          for x in vad], 0., duration)


def _selected_cancel_metrics(cancellation) -> dict:
    base = cancellation.as_dict()
    comparison = cancellation.backend_comparison or {}
    selected = next((x for x in comparison.get("candidates", [])
                     if x["backend"] == cancellation.backend), {})
    return base | selected


def run_profiled(profile: TemplateProfile, duet_path: str | Path, output_path: str | Path,
                 config: dict, pair_id: str | None = None) -> dict:
    started = time.perf_counter()
    source = Path(duet_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    duet_info, duet = normalize_audio(source, output/"duet_normalized.wav")
    duration = len(duet)/SAMPLE_RATE
    visual = align_video(profile.anchor_times, profile.visual_fingerprints, source, config["visual"])
    _write_json(output/"visual_alignment.json", visual.as_dict())
    warnings = list(visual.warnings)
    audio_alignment = None
    if visual.status == "ok":
        a, b, alignment_mode = visual.a, visual.b, "VISUAL"
    else:
        audio_alignment = align(profile.reference_audio, duet, SAMPLE_RATE, config["alignment"])
        if audio_alignment.status == "ok":
            a, b, alignment_mode = audio_alignment.a, audio_alignment.b, "AUDIO"
            warnings.append("Visual alignment failed; used reliable audio fallback")
        else:
            a, b, alignment_mode = visual.a, visual.b, "UNRELIABLE"
    reference = build_aligned_reference(profile.reference_audio, len(duet), SAMPLE_RATE, a, b)
    mapped_reference_vad = _mapped_vad(profile.reference_vad, a, b, duration)
    presence = measure_reference_presence(duet, reference, SAMPLE_RATE,
                                          mapped_reference_vad, config["audio_presence"])
    _write_json(output/"reference_audio_presence.json", presence.as_dict())
    # Audible reference permits a precise audio cross-check; muted audio must not be forced to align.
    if visual.status == "ok" and presence.audio_state == "REFERENCE_PRESENT":
        audio_alignment = align(profile.reference_audio, duet, SAMPLE_RATE, config["alignment"])
        if (audio_alignment.status == "ok" and abs(audio_alignment.b-visual.b) <= config["visual"]["hybrid_max_offset_disagreement_sec"]
                and abs(audio_alignment.a-visual.a) <= config["visual"]["max_time_scale_deviation"]):
            a, b, alignment_mode = audio_alignment.a, audio_alignment.b, "HYBRID"
            reference = build_aligned_reference(profile.reference_audio, len(duet), SAMPLE_RATE, a, b)
            mapped_reference_vad = _mapped_vad(profile.reference_vad, a, b, duration)
        elif audio_alignment.status != "ok":
            warnings.append("Reference audio is present but audio alignment cross-check is unreliable; retained visual timing")
        else:
            warnings.append("Visual/audio timing disagree; retained visual timing and marked review")
    alignment_ok = visual.status == "ok" or (audio_alignment is not None and audio_alignment.status == "ok")
    cancellation = None
    comparison = None
    if presence.audio_state == "CLEAN_MUTED":
        detection = duet
        selected_path, selected_backend = "RAW_DUET", "NONE"
    else:
        cancellation = cancel_reference(duet, reference, SAMPLE_RATE, config["cancellation"])
        detection = cancellation.residual
        comparison = cancellation.backend_comparison
        selected_path = "CANCELLATION_RESIDUAL_DETECTION"
        selected_backend = "AEC3" if cancellation.backend == "webrtc_aec3" else cancellation.backend.upper()
        warnings.extend(cancellation.warnings)
        if comparison:
            _write_json(output/"backend_comparison.json", comparison)
    detector = SileroDetector()
    detected = detector.infer(detection, SAMPLE_RATE)
    timestamps = detected.timestamps(config["vad"])
    np.savez_compressed(output/"vad_probabilities.npz", detection=detected.probabilities,
                        detection_samples=len(detection))
    raw_candidates = timestamps.segments
    for item in raw_candidates:
        item["confidence"] = round(mean_probability(timestamps, item["start"], item["end"]), 4)
    template_start = b
    template_end = a*profile.profile["duration_sec"]+b
    overlap_reference = [] if presence.audio_state == "CLEAN_MUTED" else mapped_reference_vad
    learners, overlaps, outside = classify(raw_candidates, overlap_reference, duration,
                                           template_start, template_end, config["segments"])
    rejected, leakage_diagnostics = [], []
    if presence.audio_state != "CLEAN_MUTED" and cancellation is not None:
        learners, rejected, leakage_diagnostics = diagnose(
            learners, mapped_reference_vad, duet, reference, detection, SAMPLE_RATE,
            cancellation.estimated_reference_gain, config["leakage"], full_diagnostics=False)
        if rejected:
            overlaps = overlap_intersections(learners, mapped_reference_vad,
                                             config["segments"]["overlap_min_duration_sec"])
            warnings.append(f"Filtered {len(rejected)} strong reference-leakage candidate(s)")
    write_wav(output/"residual_detection.wav", detection)
    _write_json(output/"learner_segments.json", learners)
    _write_json(output/"leakage_diagnostics.json", leakage_diagnostics)
    cancel_metrics = _selected_cancel_metrics(cancellation) if cancellation else None
    learner_duration = sum(x["end"]-x["start"] for x in learners)
    scope = contamination_scope(presence.features, learners, alignment_ok, presence.audio_state)
    audio_quality = measure_audio_quality(duet, SAMPLE_RATE, learners)
    interference = background_interference(audio_quality, config["audio_quality"])
    weak_speech = low_speech_level(audio_quality, config["audio_quality"])
    score = decide_scorability(alignment_ok, presence.audio_state, cancel_metrics,
        learner_duration, duration, len(rejected), len(overlaps), config["scorability"],
        scope, interference, weak_speech)
    if alignment_mode == "VISUAL" and audio_alignment is not None and audio_alignment.status == "ok" and presence.audio_state == "REFERENCE_PRESENT":
        score["quality_gate"] = "AMBER"
        score["quality_gate_reasons"].append("ALIGNMENT_DOMAIN_DISAGREEMENT")
    result = {
        "pipeline_version": "P1.4", "pair_id": pair_id,
        "status": "ok" if alignment_ok else "template_alignment_unreliable",
        "template_id": profile.template_id, "duet_path": str(source),
        "input_metadata": {"duet": duet_info.as_dict(), "normalized_sample_rate": SAMPLE_RATE},
        "alignment_mode": alignment_mode, "visual_alignment": visual.as_dict(),
        "audio_alignment": audio_alignment.as_dict() if audio_alignment else None,
        "timeline_mapping": {"a": a, "b": b},
        **presence.as_dict(),
        "reference_contamination_scope": scope,
        "audio_quality_features": audio_quality,
        "background_interference": interference,
        "low_speech_level": weak_speech,
        "selected_audio_path": selected_path,
        "selected_cancellation_backend": selected_backend,
        "cancellation_diagnostics": cancel_metrics,
        "backend_comparison": comparison,
        **score,
        "learner_segments": learners, "learner_duration_sec": learner_duration,
        "overlap_candidates": overlaps, "outside_template_detections": outside,
        "reference_leakage_candidates": rejected,
        "leakage_diagnostics": leakage_diagnostics,
        "suspicious_intervals": ([dict(x) | {"reason": "REFERENCE_LEAKAGE"} for x in rejected] +
                                 [dict(x) | {"reason": "POSSIBLE_TRUE_OVERLAP"} for x in overlaps] +
                                 [dict(x) | {"reason": "OUTSIDE_TEMPLATE"} for x in outside]),
        "warnings": list(dict.fromkeys(warnings)),
        "runtime_sec": time.perf_counter()-started,
        "artifacts": {name: str(output/name) for name in ["result.json", "visual_alignment.json",
            "reference_audio_presence.json", "learner_segments.json", "leakage_diagnostics.json",
            "duet_normalized.wav", "residual_detection.wav", "vad_probabilities.npz"]},
    }
    _write_json(output/"result.json", result)
    return result
