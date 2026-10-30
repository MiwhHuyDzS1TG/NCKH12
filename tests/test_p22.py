import hashlib
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from speaking_evidence.audio import sha256_file
from speaking_evidence.p22 import (AMBER_IDS, ASR_AUDIT_IDS, DISCLAIMER, GREEN_IDS, RATING_IDS,
    WAITING_FOR_HUMAN_CALIBRATION, WAITING_FOR_TARGET_CONFIRMATION, align_completeness,
    apply_mapping, calibrate, calibration_readiness, compare_asr_models, confirm_target,
    fit_ridge_mapping, freeze_machine_features, generate_completeness_evidence,
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
                    "pronunciation": 3, "intelligibility": 3, "prosody": 3}, "", True)
    saved = save_rating(rating_path, "T001-D009", "SCORABLE", {"fluency": 2,
                        "pronunciation": 4, "intelligibility": 3, "prosody": 4},
                        "learner repeated a line", True, pronunciation_examples="worked")
    assert (saved["fluency"], saved["pronunciation"], saved["intelligibility"],
            saved["prosody"]) == (2, 4, 3, 4)
    assert saved["pronunciation_examples"] == "worked"
    assert saved["note"] == "learner repeated a line"
    restarted_payload = json.loads(rating_path.read_text(encoding="utf-8"))
    restarted_item = restarted_payload["items"][0]
    assert restarted_item["human_confirmed"] is True
    assert (restarted_item["fluency"], restarted_item["pronunciation"],
            restarted_item["intelligibility"], restarted_item["prosody"]) == (2, 4, 3, 4)
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


def test_completeness_waits_for_confirmed_target(tmp_path):
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"human_confirmed": False, "confirmed_text": None}), encoding="utf-8")
    result = generate_completeness_evidence(tmp_path / "ground", tmp_path / "evidence", target)
    assert result["status"] == WAITING_FOR_TARGET_CONFIRMATION
    assert result["processed_ids"] == []


def test_calibration_waits_without_human_labels_and_writes_no_scores(tmp_path):
    ground = tmp_path / "ground"
    ground.mkdir()
    ratings = [{"pair_id": pair_id, "quality_gate": "GREEN", "amber_scorability": "NOT_REQUIRED",
                "fluency": None, "pronunciation": None, "intelligibility": None, "prosody": None,
                "human_confirmed": False} for pair_id in RATING_IDS]
    (ground / "ratings_v1.json").write_text(json.dumps({"holdout_used": False, "items": ratings}),
                                             encoding="utf-8")
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"human_confirmed": True, "confirmed_text": "one two"}),
                      encoding="utf-8")
    output = tmp_path / "output"
    result = calibrate(ground, tmp_path / "evidence", target, tmp_path / "calibration", output)
    assert result["status"] == WAITING_FOR_HUMAN_CALIBRATION
    assert result["scores"] == []
    assert not (output / "calibration_summary.json").exists()


def test_calibration_gate_rejects_non_queue_id_and_requires_variation():
    rows = [{"pair_id": pair_id, "human_confirmed": True, "amber_scorability": "NOT_REQUIRED",
             "fluency": 3, "pronunciation": 3, "intelligibility": 3, "prosody": 3}
            for pair_id in RATING_IDS[:8]]
    waiting = calibration_readiness(rows)
    assert waiting["status"] == WAITING_FOR_HUMAN_CALIBRATION
    assert any("distinct" in reason for reason in waiting["reasons"])
    with pytest.raises(ValueError, match="non-development"):
        calibration_readiness(rows + [{**rows[0], "pair_id": "T001-D001"}])


@pytest.mark.skipif(not Path("assessment_runs/T001_p22_calibrated_v01/selected_backend_evidence_summary.json").is_file(),
                    reason="private real-media development artifacts are not distributed")
def test_p22b_prepared_artifacts_are_development_only_and_raw_source():
    evidence = Path("assessment_runs/T001_p22_calibrated_v01")
    completeness = json.loads((evidence / "reading_completeness_summary_v1.json").read_text(encoding="utf-8"))
    frozen = json.loads(Path("calibration/p22b_prep_v01/feature_spec_v1.json").read_text(encoding="utf-8"))
    assert completeness["processed_ids"] == list(RATING_IDS)
    assert completeness["holdout_processed"] is False
    assert completeness["score_created"] is False
    assert frozen["status"] == "FROZEN_PRE_HUMAN_CALIBRATION"
    assert frozen["rating_count_read"] == 0
    assert frozen["holdout_processed"] is False
    assert frozen["specification"]["canonical_audio_source_required"] == "RAW_COMPLETED_DUET"
    assert all(item["intelligibility"]["recognition_stability"] is None for item in frozen["items"])
    ratings = json.loads(Path("human_ground_truth/p22a_v1/ratings_v1.json").read_text(encoding="utf-8"))
    assert all(not item["human_confirmed"] and item["fluency"] is None for item in ratings["items"])


@pytest.mark.skipif(not Path("human_ground_truth/p22a_v1/ratings_v1.json").is_file(),
                    reason="private human workflow artifacts are not distributed")
def test_phase2_result_ui_shows_waiting_without_numeric_score():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60)
    app.query_params["mode"] = "p22result"
    app.run()
    assert not app.exception
    messages = [element.value for element in app.error]
    assert "WAITING FOR HUMAN CALIBRATION" in messages
    assert not Path("assessment_runs/T001_p22_calibrated_v01/calibration_summary.json").exists()


@pytest.mark.skipif(not Path("human_ground_truth/p22a_v1/ratings_v1.json").is_file(),
                    reason="private human workflow artifacts are not distributed")
def test_teacher_rating_page_is_focused_and_machine_score_blind():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60)
    app.query_params["mode"] = "teacher"
    app.run()
    assert not app.exception
    assert any(title.value == "Teacher Rating — P2.2A" for title in app.title)
    assert any(button.label == "Save & Next" for button in app.button)
    rendered = " ".join(str(element.value) for group in
                        (app.title, app.caption, app.markdown, app.info, app.warning, app.error)
                        for element in group)
    assert all(term not in rendered.lower() for term in
               ("machine score", "asr confidence", "openpronounce", "wpm", "pause statistics", "gopt"))
    labels = {selectbox.label for selectbox in app.selectbox}
    assert {"Fluency 1–5", "Pronunciation 1–5", "Intelligibility 1–5", "Prosody 1–5"} <= labels
