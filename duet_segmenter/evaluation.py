"""Optional frame-level labeled-CSV evaluation; never changes predictions."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

LABELS = {"ORIGINAL", "LEARNER", "OVERLAP", "SILENCE", "OUTSIDE_TEMPLATE"}


def load_ground_truth(path: str | Path, duration: float) -> list[dict]:
    rows = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not {"start", "end", "label"}.issubset(reader.fieldnames):
            raise ValueError("Ground truth CSV needs start,end,label columns")
        for line, row in enumerate(reader, start=2):
            try:
                start, end = float(row["start"]), float(row["end"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid timestamps on ground truth line {line}") from exc
            label = row["label"].strip().upper()
            if label not in LABELS or start < 0 or end <= start or end > duration+0.05:
                raise ValueError(f"Invalid ground truth interval/label on line {line}: {row}")
            rows.append({"start": start, "end": min(end, duration), "label": label})
    return rows


def _mask(intervals: list[dict], frames: np.ndarray) -> np.ndarray:
    mask = np.zeros(len(frames), dtype=bool)
    for item in intervals:
        mask |= (frames >= item["start"]) & (frames < item["end"])
    return mask


def evaluate(predicted: list[dict], overlaps: list[dict], outside: list[dict],
             truth: list[dict], duration: float, cfg: dict) -> dict:
    frame = float(cfg["frame_sec"])
    centers = np.arange(frame/2, duration, frame)
    gt = {label: _mask([x for x in truth if x["label"] == label], centers) for label in LABELS}
    labeled = np.logical_or.reduce(list(gt.values()))
    predicted_mask = _mask(predicted, centers)
    learner_gt = gt["LEARNER"] | gt["OVERLAP"]
    tp = int(np.count_nonzero(predicted_mask & learner_gt & labeled))
    fp = int(np.count_nonzero(predicted_mask & ~learner_gt & labeled))
    fn = int(np.count_nonzero(~predicted_mask & learner_gt & labeled))
    precision = tp/(tp+fp) if tp+fp else None
    recall = tp/(tp+fn) if tp+fn else None
    f1 = 2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    original_count = int(np.count_nonzero(gt["ORIGINAL"]))
    overlap_count = int(np.count_nonzero(gt["OVERLAP"]))
    outside_count = int(np.count_nonzero(gt["OUTSIDE_TEMPLATE"]))
    raw_outside = _mask(outside, centers)
    # LEARNER -> OVERLAP transitions are still continuous learner activity;
    # compare only compatible outer starts and ends.
    gt_activity = sorted((x for x in truth if x["label"] in {"LEARNER", "OVERLAP"}), key=lambda x: x["start"])
    continuous = []
    for item in gt_activity:
        if continuous and item["start"] <= continuous[-1]["end"]+frame/2:
            continuous[-1]["end"] = max(continuous[-1]["end"], item["end"])
        else:
            continuous.append({"start": item["start"], "end": item["end"]})
    predicted_starts = [x["start"] for x in predicted]
    predicted_ends = [x["end"] for x in predicted]
    errors = []
    tolerance = cfg["boundary_match_tolerance_sec"]
    for item in continuous:
        for boundary, possible in ((item["start"], predicted_starts), (item["end"], predicted_ends)):
            if possible:
                error = min(abs(boundary-p) for p in possible)
                if error <= tolerance:
                    errors.append(error)
    return {
        "frame_sec": frame,
        "learner_precision": precision,
        "learner_recall": recall,
        "learner_f1": f1,
        "original_contamination_rate": float(np.count_nonzero(predicted_mask & gt["ORIGINAL"]))/original_count if original_count else None,
        "overlap_recall": float(np.count_nonzero(predicted_mask & gt["OVERLAP"]))/overlap_count if overlap_count else None,
        "false_speech_outside_template": float(np.count_nonzero(raw_outside & gt["OUTSIDE_TEMPLATE"]))/outside_count if outside_count else None,
        "median_boundary_error_sec": float(np.median(errors)) if errors else None,
        "matched_boundary_count": len(errors),
        "frame_counts": {"true_positive": tp, "false_positive": fp, "false_negative": fn},
        "labeled_frame_count": int(np.count_nonzero(labeled)),
        "metric_definitions": {
            "original_contamination_rate": "fraction of ORIGINAL-only frames predicted as learner",
            "false_speech_outside_template": "fraction of OUTSIDE_TEMPLATE frames with raw residual VAD (before rejection)",
            "boundary_error": "nearest learner/overlap reference boundary within matching tolerance",
        },
    }


def provisional_gates(metrics: dict) -> dict:
    limits = {"learner_precision": (0.95, ">="), "learner_recall": (0.95, ">="),
              "original_contamination_rate": (0.03, "<="), "median_boundary_error_sec": (0.25, "<=")}
    return {key: None if metrics[key] is None else (metrics[key] >= limit if direction == ">=" else metrics[key] <= limit)
            for key, (limit, direction) in limits.items()}
