"""Interpretable timing measurements, never proficiency scores."""
from __future__ import annotations

import re
from statistics import mean, median

FILLERS = {"um", "uh", "erm", "er", "hmm"}


def measure_fluency(turn: dict, words: list[dict], pause_min_sec: float = 0.25,
                    long_pause_sec: float = 0.70) -> dict:
    if not 0 < pause_min_sec <= long_pause_sec:
        raise ValueError("Require 0 < pause_min_sec <= long_pause_sec")
    duration = float(turn["end_sec"] - turn["start_sec"])
    intervals = turn["learner_intervals"]
    speech_duration = sum(i["end"] - i["start"] for i in intervals)
    gaps = [max(0.0, words[j]["start_sec"] - words[j-1]["end_sec"])
            for j in range(1, len(words))]
    pauses = [gap for gap in gaps if gap >= pause_min_sec]
    # A run ends at an observed pause; no gap across different task turns enters here.
    run_lengths = []
    if words:
        length = 1
        for gap in gaps:
            if gap >= pause_min_sec:
                run_lengths.append(length)
                length = 1
            else:
                length += 1
        run_lengths.append(length)
    pause_total = min(duration, sum(pauses))
    count = len(words)
    filled = sum(re.sub(r"[^a-z]", "", w["text"].lower()) in FILLERS for w in words)
    return {
        "turn_duration_sec": round(duration, 3),
        "detected_speech_duration_sec": round(speech_duration, 3),
        "phonation_ratio": round(min(1.0, speech_duration / duration), 4) if duration else 0.0,
        "word_count": count,
        "speech_rate_wpm": round(60 * count / duration, 2) if duration else 0.0,
        "articulation_rate_wpm": round(60 * count / speech_duration, 2) if speech_duration else 0.0,
        "inter_word_gaps_sec": [round(g, 3) for g in gaps],
        "pause_durations_sec": [round(p, 3) for p in pauses],
        "pause_count": len(pauses), "pause_total_sec": round(pause_total, 3),
        "pause_ratio": round(min(1.0, pause_total / duration), 4) if duration else 0.0,
        "mean_pause_duration_sec": round(mean(pauses), 3) if pauses else 0.0,
        "median_pause_duration_sec": round(median(pauses), 3) if pauses else 0.0,
        "long_pause_count": sum(p >= long_pause_sec for p in pauses),
        "longest_pause_sec": round(max(pauses, default=0.0), 3),
        "run_lengths_words": run_lengths,
        "mean_length_of_run_words": round(mean(run_lengths), 2) if run_lengths else 0.0,
        "filled_pause_count_proxy": filled,
    }


def aggregate_fluency(turns: list[dict], pause_min_sec: float,
                      long_pause_sec: float) -> dict:
    if not turns:
        return {"turn_count": 0, "word_count": 0}
    # Preserve task boundaries: only within-turn gaps are considered.
    active = sum(t["fluency"]["turn_duration_sec"] for t in turns)
    speech = sum(t["fluency"]["detected_speech_duration_sec"] for t in turns)
    words = sum(t["fluency"]["word_count"] for t in turns)
    pauses = [p for t in turns for p in t["fluency"]["pause_durations_sec"]]
    run_lengths = [length for t in turns for length in t["fluency"]["run_lengths_words"]]
    return {"turn_count": len(turns), "active_turn_duration_sec": round(active, 3),
            "detected_speech_duration_sec": round(speech, 3), "word_count": words,
            "phonation_ratio": round(min(1, speech / active), 4) if active else 0,
            "speech_rate_wpm": round(60 * words / active, 2) if active else 0,
            "articulation_rate_wpm": round(60 * words / speech, 2) if speech else 0,
            "pause_count": len(pauses), "pause_total_sec": round(sum(pauses), 3),
            "pause_ratio": round(min(1, sum(pauses) / active), 4) if active else 0,
            "long_pause_count": sum(p >= long_pause_sec for p in pauses),
            "longest_pause_sec": round(max(pauses, default=0), 3),
            "mean_length_of_run_words": round(mean(run_lengths), 2) if run_lengths else 0,
            "filled_pause_count_proxy": sum(t["fluency"]["filled_pause_count_proxy"] for t in turns),
            "pause_min_sec": pause_min_sec, "long_pause_sec": long_pause_sec}
