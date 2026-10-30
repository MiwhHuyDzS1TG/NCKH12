import hashlib
import json
from pathlib import Path

import pytest

from speaking_evidence.audio import sha256_file
from speaking_evidence.p22 import (AMBER_IDS, ASR_AUDIT_IDS, DISCLAIMER, GREEN_IDS, RATING_IDS,
    align_completeness, apply_mapping, compare_asr_models, confirm_target, fit_ridge_mapping,
    save_asr_reference, save_rating)


@pytest.mark.skipif(not Path("cohort_runs/T001_p14/data_split_v2.json").is_file(),
                    reason="private real-media development artifacts are not distributed")
def test_real_p22_queues_exclude_holdout_and_red():
    cohort = Path("cohort_runs/T001_p14")
    split = json.loads((cohort / "data_split_v2.json").read_text(encoding="utf-8"))
    rows = json.loads((cohort / "development_manifest_v3.json").read_text(encoding="utf-8"))
    by_id = {row["pair_id"]: row for row in rows}
    assert set(RATING_IDS) <= set(split["development"])
    assert set(RATING_IDS).isdisjoint(split["holdout"])
    assert all(by_id[pair_id]["quality_gate"] != "RED" for pair_id in RATING_IDS)
    assert len(GREEN_IDS) == 9 and len(AMBER_IDS) == 3
    assert set(ASR_AUDIT_IDS) <= set(GREEN_IDS)


@pytest.mark.skipif(not Path("task_profiles/T001_target_text_v1.json").is_file(),
                    reason="private real-media development artifacts are not distributed")
def test_template_is_source_only_and_students_come_from_duets():
    target = json.loads(Path("task_profiles/T001_target_text_v1.json").read_text(encoding="utf-8"))
    assert target["template_path"] == "data/templates/T001/original.mp4"
    assert target["template_sha256"] == sha256_file(Path(target["template_path"]))
    assert isinstance(target["human_confirmed"], bool)
    if target["human_confirmed"]:
        assert target["status"] == "HUMAN_CONFIRMED"
        assert target["confirmed_text"]
        assert target["machine_candidate"]
    else:
        assert target["confirmed_text"] is None
    ratings = json.loads(Path("human_ground_truth/p22a_v1/ratings_v1.json").read_text(encoding="utf-8"))
    assert all(item["pair_id"].startswith("T001-D") for item in ratings["items"])
    assert not any(item["pair_id"] == "T001" for item in ratings["items"])
    for pair_id in RATING_IDS:
        raw = json.loads((Path("assessment_runs/T001_p22_calibrated_v01/pairs") / pair_id /
                          "raw_evidence.json").read_text(encoding="utf-8"))
        assert "data\\duets\\T001" in raw["raw_duet_path"] or "data/duets/T001" in raw["raw_duet_path"]
        assert raw["canonical_source"] == "RAW_COMPLETED_DUET"
        assert raw["template_path"] == "data/templates/T001/original.mp4"


def test_human_text_is_preserved_verbatim_and_original_asr_immutable(tmp_path):
    path = tmp_path / "reference.json"
    original = {"pair_id": "T001-D005", "status": "UNREVIEWED", "human_confirmed": False,
                "original_asr": {"verbatim_transcript": "I goed home."},
                "human_verbatim_text": None}
    path.write_text(json.dumps(original), encoding="utf-8")
    text = "Um, I goed  home..."
    saved = save_asr_reference(path, text, True)
    assert saved["human_verbatim_text"] == text
    assert saved["original_asr"] == original["original_asr"]


def test_wer_model_comparison_refuses_unconfirmed_human_reference(tmp_path):
    root = tmp_path / "human"
    for pair_id in ASR_AUDIT_IDS:
        folder = root / "asr_reference_v1" / pair_id
        folder.mkdir(parents=True)
        (folder / "reference.json").write_text(json.dumps({"human_confirmed": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="Human reference missing"):
        compare_asr_models(root, tmp_path / "evidence", tmp_path / "config.yaml", tmp_path / "calibration")


def test_rating_save_does_not_modify_raw_evidence(tmp_path):
    rating_path = tmp_path / "ratings.json"
    rating_path.write_text(json.dumps({"items": [{"pair_id": "T001-D009", "quality_gate": "AMBER",
        "amber_scorability": "PENDING", "fluency": None, "intelligibility": None, "prosody": None,
        "note": "", "human_confirmed": False}]}), encoding="utf-8")
    raw = tmp_path / "raw_evidence.json"
    raw.write_bytes(b"immutable raw measurements")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        save_rating(rating_path, "T001-D009", "PENDING", {"fluency": 3,
                    "intelligibility": 3, "prosody": 3}, "", True)
    saved = save_rating(rating_path, "T001-D009", "SCORABLE", {"fluency": 2,
                        "intelligibility": 3, "prosody": 4}, "learner repeated a line", True)
    assert (saved["fluency"], saved["intelligibility"], saved["prosody"]) == (2, 3, 4)
    assert saved["note"] == "learner repeated a line"
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == digest


def test_completeness_is_transparent_and_warns_about_asr():
    result = align_completeness("one two three four", "one three extra four", "HUMAN_VERBATIM")
    assert [x["word"] for x in result["matched_sequence"]] == ["one", "three", "four"]
    assert result["omissions"] == [{"word": "two", "target_index": 1}]
    assert result["insertions"] == [{"word": "extra", "learner_index": 2}]
    assert result["coverage"] == .75
    assert "not proven" in result["warning"]


def test_score_mapping_is_deterministic_and_preliminary_only():
    rows = []
    names = ("x1", "x2")
    for i in range(10):
        rows.append({"fluency": i % 5 + 1, "x1": float(i), "x2": float((i * 3) % 7)})
    first = fit_ridge_mapping(rows, "fluency", names)
    second = fit_ridge_mapping(rows, "fluency", names)
    assert first == second
    assert 1 <= apply_mapping(first, {"x1": 4.0, "x2": 5.0}) <= 5
    assert first["status"] == "DEVELOPMENT_PRELIMINARY"
    assert DISCLAIMER == ["DEVELOPMENT / PRELIMINARY CALIBRATION", "NOT CEFR", "NOT B2", "NOT IELTS"]


def test_target_confirmation_keeps_machine_candidate(tmp_path):
    path = tmp_path / "T001_target_text_v1.json"
    candidate = {"status": "CANDIDATE", "human_confirmed": False,
                 "machine_candidate": "machine words", "confirmed_text": None}
    path.write_text(json.dumps(candidate), encoding="utf-8")
    result = confirm_target(candidate, "Human heard words exactly.", path)
    assert result["machine_candidate"] == "machine words"
    assert result["confirmed_text"] == "Human heard words exactly."
    assert result["human_confirmed"] is True
