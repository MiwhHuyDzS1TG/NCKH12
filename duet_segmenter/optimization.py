"""Deterministic, labeled development search over cached VAD probabilities."""
from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from .alignment import build_aligned_reference
from .evaluation import evaluate, load_ground_truth
from .leakage import diagnose
from .segments import classify, clip_segments, overlap_intersections
from .vad import ProbabilityCache, SileroDetector, mean_probability


def _cache(run_dir: Path) -> tuple[ProbabilityCache, ProbabilityCache]:
    path = run_dir/"vad_probabilities.npz"
    if path.exists():
        data = np.load(path)
        return (ProbabilityCache(data["residual"], int(data["residual_samples"])),
                ProbabilityCache(data["original"], int(data["original_samples"])))
    residual, _ = sf.read(run_dir/"residual_detection.wav", dtype="float32")
    original, _ = sf.read(run_dir/"original_normalized.wav", dtype="float32")
    detector = SileroDetector()
    caches = detector.infer(residual, 16_000), detector.infer(original, 16_000)
    np.savez_compressed(path, residual=caches[0].probabilities, original=caches[1].probabilities,
                        residual_samples=len(residual), original_samples=len(original))
    return caches


def predict_candidate(run_dir: str | Path, result: dict, config: dict,
                      caches: tuple[ProbabilityCache, ProbabilityCache] | None = None,
                      audio: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None) -> dict:
    run_dir = Path(run_dir)
    residual_cache, original_cache = caches or _cache(run_dir)
    residual_vad = residual_cache.timestamps(config["vad"])
    original_vad = original_cache.timestamps(config["vad"])
    alignment = result["alignment_diagnostics"]
    duration = result["timeline"]["duet_duration_sec"]
    mapped_original = clip_segments([{"start": alignment["a"]*s["start"]+alignment["b"],
                                      "end": alignment["a"]*s["end"]+alignment["b"]}
                                     for s in original_vad.segments], 0., duration)
    for item in residual_vad.segments:
        item["confidence"] = round(mean_probability(residual_vad, item["start"], item["end"]), 4)
    learners, overlaps, outside = classify(residual_vad.segments, mapped_original, duration,
        alignment["b"], alignment["a"]*result["input_metadata"]["original"]["duration_sec"]+alignment["b"],
        config["segments"])
    if audio is None:
        near, _ = sf.read(run_dir/"duet_normalized.wav", dtype="float32")
        residual, _ = sf.read(run_dir/"residual_detection.wav", dtype="float32")
        original, _ = sf.read(run_dir/"original_normalized.wav", dtype="float32")
        reference = build_aligned_reference(original, len(near), 16_000, alignment["a"], alignment["b"])
    else:
        near, residual, reference = audio
    learners, rejected, diagnostics = diagnose(learners, mapped_original, near, reference, residual,
        16_000, result["cancellation_diagnostics"]["estimated_reference_gain"], config["leakage"],
        full_diagnostics=False)
    if rejected:
        overlaps = overlap_intersections(learners, mapped_original, config["segments"]["overlap_min_duration_sec"])
    return {"learner_segments": learners, "overlap_candidates": overlaps,
            "outside_template_detections": outside, "leakage_diagnostics": diagnostics,
            "reference_leakage_candidates": rejected}


def _rank(row: dict) -> tuple:
    def value(key, default):
        item = row.get(key)
        return default if item is None else item
    return (int(value("learner_recall", 0.) >= .95),
            int(value("original_contamination_rate", 1.) <= .03),
            value("learner_f1", 0.),
            -value("median_boundary_error_sec", 99.),
            -row["fragmentation_count"], -row["false_positive_duration_sec"],
            -row["missed_learner_duration_sec"], -row["candidate_index"])


def optimize_vad(run_dir: str | Path, result: dict, config: dict,
                 full_video_reviewed: bool = False) -> dict:
    run_dir = Path(run_dir)
    truth_path = run_dir/"ground_truth.csv"
    if not truth_path.is_file():
        raise FileNotFoundError("Human ground_truth.csv is required before optimizing VAD")
    truth = load_ground_truth(truth_path, result["timeline"]["duet_duration_sec"])
    if not any(row["label"] in {"LEARNER", "OVERLAP"} for row in truth):
        raise ValueError("At least one human-labeled learner interval is required")
    caches = _cache(run_dir)
    near, _ = sf.read(run_dir/"duet_normalized.wav", dtype="float32")
    residual, _ = sf.read(run_dir/"residual_detection.wav", dtype="float32")
    original, _ = sf.read(run_dir/"original_normalized.wav", dtype="float32")
    alignment = result["alignment_diagnostics"]
    reference = build_aligned_reference(original, len(near), 16_000, alignment["a"], alignment["b"])
    audio = near, residual, reference
    baseline = (config["vad"]["threshold"], config["vad"]["min_speech_duration_ms"],
                config["vad"]["min_silence_duration_ms"], config["vad"]["speech_pad_ms"],
                config["segments"]["merge_gap_sec"])
    coarse = itertools.product((.35, .50, .65), (100, 250, 400), (50, 200, 400),
                               (0, 50, 100), (.05, .25, .50))
    candidates, seen = [], set()
    def measure(parameters, stage):
        key = tuple(parameters)
        if key in seen:
            return
        seen.add(key)
        cfg = json.loads(json.dumps(config))
        threshold, speech, silence, pad, gap = key
        cfg["vad"].update(threshold=float(threshold), min_speech_duration_ms=int(speech),
                          min_silence_duration_ms=int(silence), speech_pad_ms=int(pad))
        cfg["segments"]["merge_gap_sec"] = float(gap)
        prediction = predict_candidate(run_dir, result, cfg, caches, audio)
        metrics = evaluate(prediction["learner_segments"], prediction["overlap_candidates"],
                           prediction["outside_template_detections"], truth,
                           result["timeline"]["duet_duration_sec"], cfg["evaluation"])
        counts = metrics["frame_counts"]
        row = {"candidate_index": len(candidates), "stage": stage, "parameters": {
            "threshold": threshold, "min_speech_duration_ms": speech,
            "min_silence_duration_ms": silence, "speech_pad_ms": pad, "merge_gap_sec": gap},
            **{name: metrics[name] for name in ("learner_precision", "learner_recall", "learner_f1",
                "original_contamination_rate", "median_boundary_error_sec")},
            "false_positive_duration_sec": counts["false_positive"]*metrics["frame_sec"],
            "missed_learner_duration_sec": counts["false_negative"]*metrics["frame_sec"],
            "fragmentation_count": len(prediction["learner_segments"]),
            "leakage_filtered_count": len(prediction["reference_leakage_candidates"])}
        candidates.append(row)
    measure(baseline, "BASELINE")
    for parameters in coarse:
        measure(parameters, "COARSE")
    best_coarse = sorted(candidates, key=_rank, reverse=True)[:3]
    for winner in best_coarse:
        p = winner["parameters"]
        fine = itertools.product(
            sorted(set(round(max(.35, min(.70, p["threshold"]+delta)), 2) for delta in (-.05, 0, .05))),
            sorted(set(max(100, min(400, p["min_speech_duration_ms"]+delta)) for delta in (-75, 0, 75))),
            sorted(set(max(50, min(400, p["min_silence_duration_ms"]+delta)) for delta in (-75, 0, 75))),
            sorted(set(max(0, min(100, p["speech_pad_ms"]+delta)) for delta in (-25, 0, 25))),
            sorted(set(round(max(.05, min(.50, p["merge_gap_sec"]+delta)), 2) for delta in (-.10, 0, .10))))
        for parameters in fine:
            measure(parameters, "FINE")
    ranked = sorted(candidates, key=_rank, reverse=True)
    def dominates(a, b):
        axes = (("learner_recall", 1), ("learner_f1", 1),
                ("original_contamination_rate", -1),
                ("median_boundary_error_sec", -1), ("fragmentation_count", -1))
        better_or_equal = all(direction*(a[key] if a[key] is not None else (-999 if direction == 1 else 999)) >=
                              direction*(b[key] if b[key] is not None else (-999 if direction == 1 else 999))
                              for key, direction in axes)
        strictly = any(a[key] != b[key] for key, _ in axes)
        return better_or_equal and strictly
    frontier = [row for row in ranked if not any(dominates(other, row) for other in candidates)]
    scope = "DEVELOPMENT/PARTIAL GROUND TRUTH"
    if full_video_reviewed:
        scope += " — full video checked for missed learner turns; unlabeled negative regions remain"
    report = {"validation_scope": scope, "human_ground_truth_file": str(truth_path),
              "full_video_reviewed_for_missed_speech": full_video_reviewed,
              "selection_rule": "Recall >= .95, contamination <= .03, then F1, boundary error, fragmentation and durations",
              "baseline": candidates[0], "best_development_candidate": ranked[0],
              "development_targets_met": bool(ranked[0]["learner_recall"] is not None and
                  ranked[0]["learner_recall"] >= .95 and
                  ranked[0]["original_contamination_rate"] is not None and
                  ranked[0]["original_contamination_rate"] <= .03),
              "top_candidates": ranked[:15], "pareto_candidates": frontier[:30],
              "candidate_count": len(candidates),
              "limitations": "Metrics only score labeled intervals. Accepted learner boundaries in the known sample derive from baseline predictions, so boundary/F1 measures are optimistic; one Duet cannot establish generalizable parameters."}
    (run_dir/"vad_optimization.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    with (run_dir/"vad_optimization.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["candidate_index", "stage", *candidates[0]["parameters"],
                  "learner_precision", "learner_recall", "learner_f1", "original_contamination_rate",
                  "median_boundary_error_sec", "false_positive_duration_sec", "missed_learner_duration_sec",
                  "fragmentation_count", "leakage_filtered_count"]
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        for row in candidates:
            writer.writerow({**row, **row["parameters"]})
    return report
