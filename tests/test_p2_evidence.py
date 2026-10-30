import json
from pathlib import Path

import pytest

from speaking_evidence.asr import normalize_transcript, validate_words
from speaking_evidence.audio import require_raw_source
from speaking_evidence.fluency import aggregate_fluency, measure_fluency
from speaking_evidence.profile import build_turns, validate_profile
from speaking_evidence.runner import gate_status, load_development


def test_task_profile_valid_and_rejects_overlap():
    profile = {"task_id": "B2-A", "template_id": "T001", "version": "1", "language": "en",
               "turns": [{"turn_id": "A", "start_sec": 1, "end_sec": 3,
                          "mode": "OPEN_RESPONSE", "scoring_dimensions": ["fluency"]},
                         {"turn_id": "B", "start_sec": 3.1, "end_sec": 5,
                          "mode": "CONTROLLED_READING", "target_text": "Hello"}]}
    assert validate_profile(profile, 6) is profile
    profile["turns"][1]["start_sec"] = 2.9
    with pytest.raises(ValueError, match="non-overlapping"):
        validate_profile(profile, 6)


def test_auto_fallback_grouping_is_labeled_uncertain():
    segments = [{"start": 1, "end": 2}, {"start": 2.5, "end": 3},
                {"start": 5, "end": 6}]
    mode, turns = build_turns(segments, 10, 1.2)
    assert mode == "AUTO_TURN_FALLBACK"
    assert len(turns) == 2
    assert turns[0]["learner_intervals"] == segments[:2]
    assert all(t["boundary_confidence"] == "LOW_AUTO_TURN_FALLBACK" for t in turns)


def test_fluency_preserves_turn_boundaries_and_gaps():
    turn = {"start_sec": 0, "end_sec": 4,
            "learner_intervals": [{"start": 0, "end": 1}, {"start": 2, "end": 4}]}
    words = [{"text": "Um", "start_sec": .1, "end_sec": .4},
             {"text": "I", "start_sec": .5, "end_sec": .7},
             {"text": "agree", "start_sec": 2, "end_sec": 2.5}]
    result = measure_fluency(turn, words)
    assert result["phonation_ratio"] == .75
    assert result["speech_rate_wpm"] == 45
    assert result["articulation_rate_wpm"] == 60
    assert result["pause_count"] == 1
    assert result["pause_total_sec"] == 1.3
    assert result["mean_length_of_run_words"] == 1.5
    assert result["filled_pause_count_proxy"] == 1
    other = measure_fluency({"start_sec": 10, "end_sec": 11,
                             "learner_intervals": [{"start": 10, "end": 11}]}, [])
    aggregate = aggregate_fluency([{"fluency": result}, {"fluency": other}], .25, .7)
    assert aggregate["pause_count"] == 1  # No 7.5s inter-task waiting pause.


def test_transcript_preservation_and_word_bounds():
    original = " Um,  I I   think so. "
    assert normalize_transcript(original) == "Um, I I think so."
    words = [{"start_sec": 1.1, "end_sec": 1.3}, {"start_sec": 1.4, "end_sec": 1.8}]
    validate_words(words, 1, 2)
    with pytest.raises(ValueError):
        validate_words(words[::-1], 1, 2)


def test_gate_and_residual_rejection(tmp_path):
    assert gate_status({"quality_gate": "GREEN"}) == "P2_ELIGIBLE"
    assert gate_status({"quality_gate": "AMBER"}) == "P2_REVIEW_REQUIRED"
    assert gate_status({"quality_gate": "RED"}) == "P2_BLOCKED"
    source = tmp_path / "residual_detection.wav"
    source.write_bytes(b"dummy")
    with pytest.raises(ValueError, match="Detection"):
        require_raw_source(source)


def test_holdout_cannot_enter_development_manifest(tmp_path):
    split = {"development": ["T001-D005"],
             "holdout": [f"T001-H{i:03d}" for i in range(18)]}
    (tmp_path / "data_split_v2.json").write_text(json.dumps(split), encoding="utf-8")
    manifest = [{"pair_id": "T001-D005"}]
    (tmp_path / "development_manifest_v3.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows, _, _ = load_development(tmp_path)
    assert rows == manifest
    manifest.append({"pair_id": split["holdout"][0]})
    (tmp_path / "development_manifest_v3.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="development manifest"):
        load_development(tmp_path)
