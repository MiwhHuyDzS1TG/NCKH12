"""Conservative timeline post-processing and template/overlap states."""
from __future__ import annotations

from typing import Iterable


def clip_segments(segments: Iterable[dict], start: float, end: float, min_duration: float = 0.) -> list[dict]:
    out = []
    for item in segments:
        lo, hi = max(start, float(item["start"])), min(end, float(item["end"]))
        if hi-lo >= min_duration and hi > lo:
            out.append(dict(item) | {"start": lo, "end": hi})
    return sorted(out, key=lambda x: x["start"])


def merge_segments(segments: Iterable[dict], max_gap: float, min_duration: float) -> list[dict]:
    ordered = sorted((dict(s) for s in segments if s["end"]-s["start"] >= min_duration), key=lambda x: x["start"])
    merged = []
    for item in ordered:
        if merged and item["start"]-merged[-1]["end"] <= max_gap and item.get("overlap_candidate") == merged[-1].get("overlap_candidate"):
            prev = merged[-1]
            length1, length2 = prev["end"]-prev["start"], item["end"]-item["start"]
            if "confidence" in prev and "confidence" in item:
                prev["confidence"] = (prev["confidence"]*length1+item["confidence"]*length2)/(length1+length2)
            prev["end"] = max(prev["end"], item["end"])
        else:
            merged.append(item)
    return merged


def overlap_intersections(learner: list[dict], original: list[dict], minimum: float) -> list[dict]:
    hits = []
    for segment in learner:
        for ref in original:
            lo, hi = max(segment["start"], ref["start"]), min(segment["end"], ref["end"])
            if hi-lo >= minimum and hi > lo:
                hits.append({"start": lo, "end": hi, "timeline_state": "OVERLAP_CANDIDATE"})
    return merge_segments(hits, 0., minimum)


def classify(learner: list[dict], original: list[dict], duet_duration: float,
             template_start: float, template_end: float, cfg: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Return canonical learners, overlaps, and outside-template VAD detections."""
    valid_start = max(0., template_start)
    valid_end = min(duet_duration, template_end+cfg["template_end_padding_sec"])
    outside = []
    for item in learner:
        if item["start"] < valid_start:
            outside.extend(clip_segments([item], 0., valid_start))
        if item["end"] > valid_end:
            outside.extend(clip_segments([item], valid_end, duet_duration))
    outside = [dict(s) | {"timeline_state": "OUTSIDE_TEMPLATE"} for s in outside]
    clipped = clip_segments(learner, valid_start, valid_end, cfg["min_duration_sec"])
    for item in clipped:
        item["overlap_candidate"] = any(min(item["end"], ref["end"])-max(item["start"], ref["start"]) >= cfg["overlap_min_duration_sec"] for ref in original)
    clipped = merge_segments(clipped, cfg["merge_gap_sec"], cfg["min_duration_sec"])
    overlap = overlap_intersections(clipped, original, cfg["overlap_min_duration_sec"])
    return clipped, overlap, outside
