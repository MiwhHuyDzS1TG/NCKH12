import json
from pathlib import Path

import pytest

from speaking_evidence.p21b import (AUDIT_IDS, compare_models, confirm_profile,
                                    map_profile_to_duet, propose_profile, review_profile_ai,
                                    run_confirmed)
from speaking_evidence.profile import build_turns
from speaking_evidence.fluency import aggregate_fluency, measure_fluency
from speaking_evidence.wer import word_error_counts


def _proposal_fixture(tmp_path):
    cohort = tmp_path / "cohort"
    (cohort / "template_profile").mkdir(parents=True)
    template = tmp_path / "original.mp4"
    template.write_bytes(b"fake template for profile unit test")
    from speaking_evidence.audio import sha256_file
    (cohort / "template_profile" / "profile.json").write_text(json.dumps({
        "template_id": "T001", "duration_sec": 10,
        "template_sha256": sha256_file(template)}), encoding="utf-8")
    (cohort / "template_profile" / "reference_vad.json").write_text(
        json.dumps([{"start": 0, "end": 2}]), encoding="utf-8")
    row = {"pair_id": "T001-DX", "template_id": "T001", "status": "ok", "quality_gate": "GREEN",
           "visual_alignment": {"status": "ok", "a": 1.0, "b": 0.0},
           "learner_segments": [{"start": 2, "end": 4}, {"start": 4.5, "end": 9}]}
    (cohort / "development_manifest_v3.json").write_text(json.dumps([row]), encoding="utf-8")
    (cohort / "data_split_v2.json").write_text(json.dumps({
        "development": ["T001-DX"], "holdout": [f"T001-H{i}" for i in range(18)]}), encoding="utf-8")
    return cohort, template, row


def test_candidate_and_human_confirmation_have_separate_provenance(tmp_path):
    cohort, template, _ = _proposal_fixture(tmp_path)
    candidate_path = tmp_path / "T001_v1_candidate.json"
    candidate = propose_profile(cohort, template, candidate_path)
    assert candidate["status"] == "CANDIDATE"
    assert candidate["human_confirmed"] is False
    assert candidate["source"]["holdout_used"] is False
    assert candidate["turns"][0]["mode"] == "UNKNOWN"
    assert candidate["turns"][0]["prompt_text"] == ""
    confirmed_path = tmp_path / "T001_v1.json"
    with pytest.raises(ValueError, match="explicitly confirm"):
        confirm_profile(candidate, candidate["turns"], template, confirmed_path, False)
    confirmed = confirm_profile(candidate, candidate["turns"], template, confirmed_path, True)
    assert confirmed["human_confirmed"] is True
    assert confirmed["source"]["candidate_sha256"]
    assert candidate_path.read_bytes() != confirmed_path.read_bytes()


def test_profile_mapping_intersection_excludes_waiting_from_pause(tmp_path):
    _, _, row = _proposal_fixture(tmp_path)
    row["input_metadata"] = {"duet": {"duration_sec": 10}}
    profile = {"task_id": "T001-speaking", "template_id": "T001", "version": "1", "language": "en",
               "status": "HUMAN_CONFIRMED", "human_confirmed": True,
               "turns": [{"turn_id": "A", "start_sec": 2, "end_sec": 4, "mode": "UNKNOWN"},
                         {"turn_id": "B", "start_sec": 6, "end_sec": 9, "mode": "UNKNOWN"}]}
    mapped = map_profile_to_duet(profile, row)
    mode, turns = build_turns(row["learner_segments"], 10, 1.2, mapped)
    assert mode == "MANUAL_TASK_PROFILE"
    assert turns[0]["learner_intervals"] == [{"start": 2, "end": 4}]
    assert turns[1]["learner_intervals"] == [{"start": 6, "end": 9}]
    measured = [measure_fluency(t, [{"text": "Hi", "start_sec": t["start_sec"],
                                 "end_sec": t["start_sec"] + .3}]) for t in turns]
    aggregate = aggregate_fluency([{"fluency": f} for f in measured], .25, .7)
    assert aggregate["pause_count"] == 0
    assert aggregate["active_turn_duration_sec"] == 5


def test_ai_review_keeps_human_confirmation_false_and_maps(tmp_path):
    cohort, template, row = _proposal_fixture(tmp_path)
    # The production AI reviewer demands the actual fixed nine-GREEN cohort.
    with pytest.raises(ValueError, match="nine-video"):
        review_profile_ai(propose_profile(cohort, template, tmp_path / "T001_v1_candidate.json"),
                          template, cohort, tmp_path / "T001_v2_ai.json")
    row["input_metadata"] = {"duet": {"duration_sec": 10}}
    ai_profile = {"task_id": "T001-speaking", "template_id": "T001", "version": "2",
                  "language": "en", "status": "AI_ASSISTED_CONFIRMED",
                  "model_reviewed": True, "human_confirmed": False,
                  "turns": [{"turn_id": "T001", "start_sec": 2, "end_sec": 9,
                             "mode": "CONTROLLED_READING"}]}
    mapped = map_profile_to_duet(ai_profile, row)
    assert mapped["human_confirmed"] is False
    mode, turns = build_turns(row["learner_segments"], 10, 1.2, mapped)
    assert mode == turns[0]["boundary_confidence"] == "AI_REVIEWED_TASK_PROFILE"
    ai_profile["model_reviewed"] = False
    with pytest.raises(ValueError, match="reviewed"):
        map_profile_to_duet(ai_profile, row)


def test_p21b_refuses_historical_output_overwrite(tmp_path):
    old = tmp_path / "assessment_runs" / "T001_p2"
    old.mkdir(parents=True)
    marker = old / "cohort_summary.json"
    marker.write_text("historical", encoding="utf-8")
    with pytest.raises(ValueError, match="must not overwrite"):
        run_confirmed(tmp_path, tmp_path / "profile.json", old, old, tmp_path / "p2_config.yaml")
    assert marker.read_text(encoding="utf-8") == "historical"


def test_wer_ignores_case_punctuation_and_counts_errors():
    result = word_error_counts("Um, I I like apples.", "um I like pears now")
    assert result["reference_words"] == 5
    assert result["hypothesis_words"] == 5
    assert result["substitutions"] + result["insertions"] + result["deletions"] == 3
    assert result["wer"] == .6
    assert result["reference_filler_words"] == 1
    assert word_error_counts("Hello, WORLD!", "hello world")["wer"] == 0


def test_model_comparison_reuses_identical_turn_audio_and_references(tmp_path, monkeypatch):
    out = tmp_path / "p21b"
    out.mkdir()
    (out / "sample_summary.json").write_text(json.dumps({"human_confirmed": True,
        "holdout_processed": False}), encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("asr:\n  model: small.en\n  language: en\n  beam_size: 5\n  device: cpu\n  compute_type: int8\n", encoding="utf-8")
    for pair_id in AUDIT_IDS:
        audit = out / "asr_validation" / pair_id
        audit.mkdir(parents=True)
        audio_ref = f"pairs/{pair_id}/turns/T001/model_input.wav"
        (out / audio_ref).parent.mkdir(parents=True)
        (out / audio_ref).write_bytes(b"same audio path for both models")
        turn = {"turn_id": "T001", "model_input_ref": audio_ref, "start_sec": 1, "end_sec": 2,
                "transcript": {"verbatim_transcript": "hello world", "runtime_sec": 1,
                               "words": [{"text": "hello", "start_sec": 1.1, "end_sec": 1.4},
                                         {"text": "world", "start_sec": 1.5, "end_sec": 1.8}]}}
        (audit / "asr_transcript.json").write_text(json.dumps({"pair_id": pair_id,
            "preprocessing": {"canonical_source": "RAW_COMPLETED_DUET"}, "turns": [turn]}), encoding="utf-8")
        (audit / "human_reference.json").write_text(json.dumps({"pair_id": pair_id,
            "human_confirmed": True, "turns": [{"turn_id": "T001", "reference_text": "Hello, world!"}]}), encoding="utf-8")
        evidence = out / "pairs" / pair_id / "evidence.json"
        evidence.write_text(json.dumps({"turns": [{"turn_id": "T001",
            "learner_intervals": [{"start": 1, "end": 2}]}]}), encoding="utf-8")
    seen = []
    class FakeBackend:
        def __init__(self, **kwargs):
            assert kwargs["model"] == "medium.en"
        def transcribe(self, path, start, end, intervals):
            seen.append(str(path))
            return {"verbatim_transcript": "hello world", "runtime_sec": 2,
                    "words": [{"text": "hello", "start_sec": 1.1, "end_sec": 1.4},
                              {"text": "world", "start_sec": 1.5, "end_sec": 1.8}]}
        def provenance(self):
            return {"model": "medium.en"}
    monkeypatch.setattr("speaking_evidence.p21b.FasterWhisperBackend", FakeBackend)
    result = compare_models(out, config)
    assert len(seen) == len(AUDIT_IDS)
    assert all(pair["identical_model_input_refs"] for pair in result["per_pair"])
    assert all(pair["small"]["wer"] == pair["medium"]["wer"] == 0 for pair in result["per_pair"])
    assert result["holdout_processed"] is False
