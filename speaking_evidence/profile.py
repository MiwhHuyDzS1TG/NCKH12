"""Optional manually authored task turns and explicitly uncertain fallback turns."""
from __future__ import annotations

import re
from typing import Any

MODES = {"OPEN_RESPONSE", "CONTROLLED_READING", "UNKNOWN"}
_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_profile(profile: dict[str, Any], source_duration: float | None = None) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("TaskProfile must be an object")
    for field in ("task_id", "template_id", "version", "language"):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            raise ValueError(f"TaskProfile requires {field}")
    if not isinstance(profile.get("turns"), list) or not profile["turns"]:
        raise ValueError("TaskProfile requires nonempty turns")
    previous_end = 0.0
    seen: set[str] = set()
    for turn in profile["turns"]:
        ident = turn.get("turn_id") if isinstance(turn, dict) else None
        if not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in seen:
            raise ValueError("Turn IDs must be unique safe identifiers")
        seen.add(ident)
        start, end = turn.get("start_sec"), turn.get("end_sec")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError("Turn boundaries must be numeric")
        if not (0 <= start < end) or start < previous_end - 1e-6:
            raise ValueError("Turn ranges must be positive, ordered and non-overlapping")
        if source_duration is not None and end > source_duration + 0.05:
            raise ValueError("Turn extends beyond source duration")
        previous_end = end
        if turn.get("mode") not in MODES:
            raise ValueError("Invalid turn mode")
        if not isinstance(turn.get("scoring_dimensions", []), list):
            raise ValueError("scoring_dimensions must be a list")
        for field in ("prompt_text", "target_text"):
            if field in turn and not isinstance(turn[field], str):
                raise ValueError(f"{field} must be text")
    return profile


def validate_segments(segments: list[dict], duration: float) -> list[dict]:
    ordered = sorted(segments, key=lambda s: (s["start"], s["end"]))
    previous_end = 0.0
    for segment in ordered:
        start, end = float(segment["start"]), float(segment["end"])
        if not 0 <= start < end <= duration + 0.05 or start < previous_end - 1e-6:
            raise ValueError("Phase-1 learner segments overlap or exceed source duration")
        previous_end = end
    return ordered


def build_turns(segments: list[dict], duration: float, gap_sec: float,
                profile: dict | None = None) -> tuple[str, list[dict]]:
    ordered = validate_segments(segments, duration)
    if profile is not None:
        validate_profile(profile, duration)
        profile_mode = ("AI_REVIEWED_TASK_PROFILE" if profile.get("status") == "AI_ASSISTED_CONFIRMED"
                        else "MANUAL_TASK_PROFILE")
        turns = []
        for item in profile["turns"]:
            start, end = float(item["start_sec"]), float(item["end_sec"])
            contained = [{"start": max(start, float(s["start"])),
                          "end": min(end, float(s["end"]))} for s in ordered
                         if float(s["end"]) > start and float(s["start"]) < end]
            contained = [s for s in contained if s["end"] > s["start"]]
            turns.append({"turn_id": item["turn_id"], "start_sec": start,
                          "end_sec": end, "mode": item["mode"],
                          "prompt_text": item.get("prompt_text"),
                          "target_text": item.get("target_text"),
                          "scoring_dimensions": item.get("scoring_dimensions", []),
                          "learner_intervals": contained,
                          "boundary_confidence": profile_mode})
        return profile_mode, turns
    if gap_sec < 0:
        raise ValueError("turn_group_gap_sec must be nonnegative")
    groups: list[list[dict]] = []
    for segment in ordered:
        interval = {"start": float(segment["start"]), "end": float(segment["end"])}
        if not groups or interval["start"] - groups[-1][-1]["end"] > gap_sec:
            groups.append([])
        groups[-1].append(interval)
    turns = [{"turn_id": f"T{index:03d}", "start_sec": group[0]["start"],
              "end_sec": group[-1]["end"], "mode": "UNKNOWN",
              "prompt_text": None, "target_text": None,
              "scoring_dimensions": [], "learner_intervals": group,
              "boundary_confidence": "LOW_AUTO_TURN_FALLBACK"}
             for index, group in enumerate(groups, 1)]
    return "AUTO_TURN_FALLBACK", turns
