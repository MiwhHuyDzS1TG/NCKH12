"""Local, inspectable end-to-end segmentation pipeline."""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf
import yaml

from .alignment import align, build_aligned_reference
from .cancellation import cancel_reference
from .leakage import diagnose
from .evaluation import evaluate, load_ground_truth, provisional_gates
from .media import SAMPLE_RATE, extract_duet_source_audio, normalize_audio, write_wav
from .plots import plot_alignment, plot_timeline
from .segments import classify, clip_segments
from .vad import SileroDetector, mean_probability

log = logging.getLogger(__name__)


def _clean_json(value):
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_json(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def _write_json(path: Path, value: dict | list) -> None:
    path.write_text(json.dumps(_clean_json(value), indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def load_config(path: str | Path | None = None) -> dict:
    default_path = Path(__file__).with_name("defaults.yaml")
    config = yaml.safe_load(default_path.read_text(encoding="utf-8"))
    if path is not None:
        custom = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(custom, dict):
            raise ValueError("YAML configuration must be a mapping")
        for section, values in custom.items():
            if section not in config or not isinstance(values, dict):
                raise ValueError(f"Unknown/invalid configuration section: {section}")
            unknown = set(values)-set(config[section])
            if unknown:
                raise ValueError(f"Unknown configuration keys in {section}: {sorted(unknown)}")
            config[section].update(values)
    return config


def _raw_preview(raw: np.ndarray, sr: int, learner: list[dict]) -> np.ndarray:
    crops = [raw[max(0,round(x["start"]*sr)):min(len(raw),round(x["end"]*sr))] for x in learner]
    crops = [x for x in crops if len(x)]
    if crops:
        return np.concatenate(crops, axis=0)
    return np.zeros((1,) if raw.ndim == 1 else (1, raw.shape[1]), dtype=np.float32)


def run(original_path: str | Path, duet_path: str | Path, output_path: str | Path,
        config: dict, ground_truth: str | Path | None = None,
        progress_callback: Callable[[str, float], None] | None = None) -> dict:
    def report(stage: str, progress: float) -> None:
        if progress_callback is not None:
            progress_callback(stage, progress)

    started = time.perf_counter()
    output = Path(output_path).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    report("Normalizing media", 0.05)
    original_info, original = normalize_audio(original_path, output/"original_normalized.wav")
    duet_info, duet = normalize_audio(duet_path, output/"duet_normalized.wav")
    raw_duet, raw_sr = extract_duet_source_audio(duet_path, output/"duet_source_audio.wav")
    report("Aligning known reference", 0.30)
    log.info("Normalized original %.3f s and duet %.3f s", len(original)/SAMPLE_RATE, len(duet)/SAMPLE_RATE)
    result_alignment = align(original, duet, SAMPLE_RATE, config["alignment"])
    _write_json(output/"alignment.json", result_alignment.as_dict())
    plot_alignment(result_alignment, output/"debug_alignment.png")
    report("Measuring cancellation", 0.52)
    log.info("Alignment %s: coarse %.3f s, b %.6f s, a %.8f, %d anchors",
             result_alignment.status, result_alignment.coarse_offset_sec, result_alignment.b,
             result_alignment.a, sum(x.accepted for x in result_alignment.anchors))
    warnings = list(result_alignment.warnings)
    template_start = result_alignment.b
    template_end = result_alignment.a*(len(original)/SAMPLE_RATE)+result_alignment.b
    residual = np.zeros_like(duet)
    cancellation = None
    original_vad = []
    residual_vad = []
    learners = []
    overlaps = []
    outside = []
    leakage_diagnostics = []
    leakage_rejected = []
    status = result_alignment.status
    if status == "ok":
        reference = build_aligned_reference(original, len(duet), SAMPLE_RATE,
                                             result_alignment.a, result_alignment.b)
        cancellation = cancel_reference(duet, reference, SAMPLE_RATE, config["cancellation"])
        if cancellation.backend_comparison is not None:
            _write_json(output/"backend_comparison.json", cancellation.backend_comparison)
        residual = cancellation.residual
        warnings.extend(cancellation.warnings)
        status = cancellation.status
        log.info("Cancellation %s via %s: gain %.4f, suppression %.2f dB",
                 status, cancellation.backend, cancellation.estimated_reference_gain,
                 cancellation.reference_suppression_db)
        if status == "ok":
            report("Detecting speech", 0.72)
            detector = SileroDetector()
            cached_residual = detector.infer(residual, SAMPLE_RATE)
            cached_original = detector.infer(original, SAMPLE_RATE)
            np.savez_compressed(output/"vad_probabilities.npz",
                                residual=cached_residual.probabilities,
                                original=cached_original.probabilities,
                                residual_samples=len(residual), original_samples=len(original))
            detected_residual = cached_residual.timestamps(config["vad"])
            detected_original = cached_original.timestamps(config["vad"])
            residual_vad = detected_residual.segments
            original_vad = clip_segments([{"start": result_alignment.a*s["start"]+result_alignment.b,
                                           "end": result_alignment.a*s["end"]+result_alignment.b}
                                          for s in detected_original.segments], 0., len(duet)/SAMPLE_RATE)
            for item in residual_vad:
                item["confidence"] = round(mean_probability(detected_residual, item["start"], item["end"]), 4)
            learners, overlaps, outside = classify(residual_vad, original_vad, len(duet)/SAMPLE_RATE,
                                                   template_start, template_end, config["segments"])
            learners, leakage_rejected, leakage_diagnostics = diagnose(
                learners, original_vad, duet, reference, residual, SAMPLE_RATE,
                cancellation.estimated_reference_gain, config["leakage"])
            if leakage_rejected:
                # Recompute overlap intersections from the final immutable learner prediction.
                from .segments import overlap_intersections
                overlaps = overlap_intersections(learners, original_vad, config["segments"]["overlap_min_duration_sec"])
                warnings.append(f"Filtered {len(leakage_rejected)} strong reference-leakage candidate(s); inspect diagnostics")
            log.info("VAD %d residual intervals -> %d learner intervals, %d overlap candidates, %d outside-template intervals",
                     len(residual_vad), len(learners), len(overlaps), len(outside))
            if outside:
                warnings.append(f"Rejected/flagged {len(outside)} residual speech intervals outside the mapped template")
    write_wav(output/"residual_detection.wav", residual)
    report("Writing review artifacts", 0.90)
    sf.write(output/"learner_preview.wav", _raw_preview(raw_duet, raw_sr, learners), raw_sr, subtype="PCM_16")
    plot_timeline(len(duet)/SAMPLE_RATE, original_vad, residual_vad, learners, overlaps, outside,
                  template_start, template_end, output/"debug_timeline.png")
    evaluation = None
    if ground_truth is not None:
        truth = load_ground_truth(ground_truth, len(duet)/SAMPLE_RATE)
        evaluation = evaluate(learners, overlaps, outside, truth, len(duet)/SAMPLE_RATE, config["evaluation"])
        evaluation["provisional_gates"] = provisional_gates(evaluation)
        _write_json(output/"evaluation.json", evaluation)
    _write_json(output/"learner_segments.json", learners)
    _write_json(output/"leakage_diagnostics.json", leakage_diagnostics)
    artifact_names = ["result.json", "learner_segments.json", "alignment.json", "residual_detection.wav",
        "learner_preview.wav", "debug_alignment.png", "debug_timeline.png", "original_normalized.wav",
        "duet_normalized.wav", "duet_source_audio.wav", "leakage_diagnostics.json"]
    if (output/"vad_probabilities.npz").exists():
        artifact_names.append("vad_probabilities.npz")
    artifacts = {name: str(output/name) for name in artifact_names}
    if cancellation and cancellation.backend_comparison is not None:
        artifacts["backend_comparison.json"] = str(output/"backend_comparison.json")
    if evaluation is not None:
        artifacts["evaluation.json"] = str(output/"evaluation.json")
    result = {
        "status": status,
        "input_metadata": {"original": original_info.as_dict(), "duet": duet_info.as_dict(),
                           "normalized_sample_rate": SAMPLE_RATE, "duet_source_audio_sample_rate": raw_sr,
                           "duet_source_audio_channels": 1 if raw_duet.ndim == 1 else raw_duet.shape[1]},
        "alignment_diagnostics": result_alignment.as_dict(),
        "cancellation_diagnostics": cancellation.as_dict() if cancellation else None,
        "reference_suppression_definition": "10 log10(estimated reference-correlated input energy / residual energy) in high-correlation reference-active windows; ERLE-like, not strict acoustic echo ERLE",
        "vad_configuration": config["vad"],
        "learner_segments": learners,
        "confidence_basis": "mean Silero speech probability over each candidate interval; detection strength, not calibrated speaker identity",
        "overlap_candidates": overlaps,
        "original_vad_segments": original_vad,
        "residual_vad_segments": residual_vad,
        "outside_template_detections": outside,
        "leakage_diagnostics": leakage_diagnostics,
        "reference_leakage_candidates": leakage_rejected,
        "backend_comparison": cancellation.backend_comparison if cancellation else None,
        "timeline": {"template_start_sec": max(0., template_start), "template_end_sec": min(len(duet)/SAMPLE_RATE, template_end),
                     "duet_duration_sec": len(duet)/SAMPLE_RATE, "outside_state": "OUTSIDE_TEMPLATE"},
        "evaluation": evaluation,
        "warnings": warnings,
        "runtime_sec": time.perf_counter()-started,
        "artifacts": artifacts,
    }
    _write_json(output/"result.json", result)
    report("Complete", 1.0)
    return result
