import hashlib
import json
import shutil
import wave
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from speaking_evidence.p22 import RATING_IDS
from speaking_evidence.p24_validation import (
    ORIGINAL_RATINGS_SHA256,
    PLAN_SHA256,
    RATING_SCHEMA_VERSION,
    VALIDATION_IDS,
    initialize_validation_rating_artifact,
    rating_progress,
    save_validation_rating,
)
from speaking_evidence.p24_validation_preflight import (
    MANIFEST_NAME,
    ORIGINAL_IDS,
    VERSION as PREFLIGHT_VERSION,
    build_replacement_manifest,
    validate_replacement_manifest,
)


PRIVATE_REQUIRED = (
    Path("human_ground_truth/p22a_v1/ratings_v2.json").is_file()
    and Path("assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json").is_file()
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_fixture(tmp_path: Path) -> tuple[Path, Path]:
    copies = (
        "pretrained_model_tournament_v1.json",
        "human_ground_truth/p22a_v1/ratings_v2.json",
        "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json",
        "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json",
        "cohort_runs/T001_p14/data_split_v2.json",
        "cohort_runs/T001_p14/development_manifest_v3.json",
        MANIFEST_NAME,
        "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json",
    )
    for relative in copies:
        source, destination = Path(relative), tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    summary = json.loads((tmp_path /
        "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json").read_text(
            encoding="utf-8"))
    for item in summary["items"]:
        audio = tmp_path / "assessment_runs/T001_p24_tournament_v1" / item["model_input_ref"]
        audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16_000)
            handle.writeframes(b"\x00\x00" * 160)
        item["model_input_sha256"] = _sha(audio)
    (tmp_path / "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    artifact = tmp_path / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    artifact.unlink()
    return tmp_path, artifact


def test_validation_queue_ids_are_exact_and_separate_from_calibration():
    assert VALIDATION_IDS == (
        "T001-D006", "T001-D023", "T001-D064", "T001-D043", "T001-D048"
    )
    assert set(VALIDATION_IDS).isdisjoint(RATING_IDS)


def test_frozen_preflight_keeps_all_five_scorable_amber_items():
    manifest = json.loads(Path(MANIFEST_NAME).read_text(encoding="utf-8"))
    validate_replacement_manifest(manifest)
    assert manifest["version"] == PREFLIGHT_VERSION
    assert tuple(manifest["original_five_ids"]) == ORIGINAL_IDS == VALIDATION_IDS
    assert manifest["ratings_before_audit"] == "0/5"
    assert manifest["failed_ids"] == []
    assert manifest["replacements"] == []
    assert manifest["eligible_replacement_pool"] == []
    assert manifest["deterministic_backup_ranking"] == []
    assert all(item["p1_status"] == "AMBER" for item in manifest["preflight"])
    assert all(item["teacher_rating_eligible"] is True for item in manifest["preflight"])
    assert all(item["decision"] == "KEEP" for item in manifest["preflight"])
    assert all(item["human_validation_score_used"] is False for item in manifest["preflight"])
    assert manifest["selection_uses_human_validation_scores"] is False
    assert manifest["split_proof"]["final_holdout_intersection"] == []


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_preflight_is_frozen_and_refuses_to_run_after_any_rating(tmp_path):
    root, artifact = _private_fixture(tmp_path)
    source_rating = Path(
        "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_rating, artifact)
    destination = root / "fresh_preflight.json"
    first = build_replacement_manifest(root, destination)
    frozen_bytes = destination.read_bytes()
    second = build_replacement_manifest(root, destination)
    assert second == first
    assert destination.read_bytes() == frozen_bytes
    destination.unlink()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["items"][0]["fluency"] = 4
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="has begun"):
        build_replacement_manifest(root, destination)


def test_preflight_validator_rejects_red_or_original_rating_overlap():
    payload = json.loads(Path(MANIFEST_NAME).read_text(encoding="utf-8"))
    payload["final_five_ids"][0] = RATING_IDS[0]
    with pytest.raises(ValueError, match="overlaps"):
        validate_replacement_manifest(payload)
    payload = json.loads(Path(MANIFEST_NAME).read_text(encoding="utf-8"))
    payload["preflight"][0]["p1_status"] = "RED"
    with pytest.raises(ValueError, match="not objectively scorable"):
        validate_replacement_manifest(payload)


def test_technical_replacement_provenance_must_use_frozen_ranking():
    payload = json.loads(Path(MANIFEST_NAME).read_text(encoding="utf-8"))
    failed, replacement = "T001-D006", "T001-D002"
    item = payload["preflight"][0]
    item.update({
        "p1_status": "RED",
        "scorability": "UNSCORABLE_ALIGNMENT",
        "teacher_rating_eligible": False,
        "decision": "REPLACE_TECHNICAL_FAILURE",
    })
    payload["failed_ids"] = [failed]
    payload["replacements"] = [{
        "original_id": failed,
        "replacement_id": replacement,
        "reason": "PRE_RATING_TECHNICAL_ELIGIBILITY_REPLACEMENT",
    }]
    payload["deterministic_backup_ranking"] = [{
        "pair_id": replacement,
        "rank": 1,
        "human_validation_score_used": False,
    }]
    payload["final_five_ids"][0] = replacement
    validate_replacement_manifest(payload)
    payload["replacements"][0]["replacement_id"] = "T001-D030"
    with pytest.raises(ValueError, match="frozen backup ranking"):
        validate_replacement_manifest(payload)


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_validation_queue_is_development_only_and_excludes_holdout():
    split = json.loads(Path("cohort_runs/T001_p14/data_split_v2.json").read_text(
        encoding="utf-8"))
    assert set(VALIDATION_IDS) <= set(split["development"])
    assert set(VALIDATION_IDS).isdisjoint(split["holdout"])


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_empty_artifact_is_separate_versioned_and_machine_selection_frozen(tmp_path):
    root, artifact = _private_fixture(tmp_path)
    original = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    winner = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_before, winner_before = original.read_bytes(), winner.read_bytes()
    payload = initialize_validation_rating_artifact(root, artifact)
    assert tuple(payload["queue_ids"]) == VALIDATION_IDS
    assert payload["rating_schema_version"] == RATING_SCHEMA_VERSION
    assert payload["split"] == "DEVELOPMENT_VALIDATION"
    assert payload["audio_source_type"] == "RAW_CROPPED"
    assert payload["p24_frozen_plan_sha256"] == PLAN_SHA256
    assert payload["ratings_must_not_reselect_p24_models"] is True
    assert payload["automatic_calibration_after_completion"] is False
    assert payload["automatic_merge_into_original_12"] is False
    assert rating_progress(payload) == (0, 5)
    assert all(item["human_confirmed"] is False for item in payload["items"])
    assert all(item["amber_scorability"] is None for item in payload["items"])
    assert [item["requires_teacher_scorability_confirmation"] for item in payload["items"]] == [
        True, True, False, False, False
    ]
    assert all(item[name] is None for item in payload["items"]
               for name in ("fluency", "pronunciation", "intelligibility", "prosody"))
    assert all(item["audio_source_type"] == "RAW_CROPPED" for item in payload["items"])
    assert original.read_bytes() == original_before
    assert winner.read_bytes() == winner_before
    assert len(list((artifact.parent / "rating_backups").glob("*.json"))) == 1


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_safe_save_backup_and_restart_preserve_validation_rating_only(tmp_path):
    root, artifact = _private_fixture(tmp_path)
    original = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    winner = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_hash, winner_hash = _sha(original), _sha(winner)
    initialize_validation_rating_artifact(root, artifact)
    saved = save_validation_rating(
        artifact, root, "T001-D006", "SCORABLE",
        {"fluency": 2, "pronunciation": 3, "intelligibility": 4, "prosody": 5},
        pronunciation_examples="final sound",
    )
    restarted = json.loads(Path(str(artifact)).read_text(encoding="utf-8"))
    persisted = restarted["items"][0]
    assert persisted == saved
    assert persisted["human_confirmed"] is True
    assert [persisted[name] for name in
            ("fluency", "pronunciation", "intelligibility", "prosody")] == [2, 3, 4, 5]
    assert persisted["rater_metadata"]["human_reviewed"] is True
    assert persisted["rater_metadata"]["split"] == "DEVELOPMENT_VALIDATION"
    assert rating_progress(restarted) == (1, 5)
    assert len(list((artifact.parent / "rating_backups").glob("*.json"))) == 2
    assert _sha(original) == original_hash == ORIGINAL_RATINGS_SHA256
    assert _sha(winner) == winner_hash
    assert not (root / "assessment_runs/T001_p22_calibrated_v01/calibration_summary.json").exists()


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_five_of_five_completion_does_not_merge_reselect_or_calibrate(tmp_path):
    root, artifact = _private_fixture(tmp_path)
    original = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    winner = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_before, winner_before = original.read_bytes(), winner.read_bytes()
    initialize_validation_rating_artifact(root, artifact)
    for pair_id in VALIDATION_IDS:
        save_validation_rating(
            artifact, root, pair_id, "SCORABLE",
            {"fluency": 3, "pronunciation": 3, "intelligibility": 3, "prosody": 3},
        )
    completed = json.loads(artifact.read_text(encoding="utf-8"))
    assert rating_progress(completed) == (5, 5)
    assert completed["automatic_calibration_after_completion"] is False
    assert completed["automatic_merge_into_original_12"] is False
    assert completed["ratings_must_not_reselect_p24_models"] is True
    assert original.read_bytes() == original_before
    assert winner.read_bytes() == winner_before
    assert not (root / "assessment_runs/T001_p22_calibrated_v01/calibration_summary.json").exists()
    assert not (root / "assessment_runs/T001_p25_frozen_validation_v1").exists()


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_teacher_validation_ui_is_five_item_machine_blind_and_unprefilled():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60)
    app.query_params["mode"] = "teacher_validation"
    app.run()
    assert not app.exception
    assert any(title.value == "Teacher Rating — P2.4 Development Validation"
               for title in app.title)
    rendered = " ".join(str(element.value) for group in
                        (app.title, app.caption, app.markdown, app.info, app.warning, app.error)
                        for element in group)
    assert "Development Validation: 0 / 5" in rendered
    assert all(term not in rendered.lower() for term in (
        "f0_baseline", "p0_asr_recognition", "i0_single_asr", "r0_praat",
        "micro-wer", "asr confidence", "pretrained_embedding_feature",
        "machine_calibration_unstable",
    ))
    video = app.selectbox(key="teacher_validation_pair")
    assert tuple(video.options) == VALIDATION_IDS
    assert set(video.options).isdisjoint(RATING_IDS)
    labels = {selectbox.label for selectbox in app.selectbox}
    assert {"Fluency 1–5", "Pronunciation 1–5",
            "Intelligibility 1–5", "Prosody 1–5"} <= labels
    for name in ("fluency", "pronunciation", "intelligibility", "prosody"):
        assert app.selectbox(key=f"teacher_validation_{name}_T001-D006").value is None
    assert app.selectbox(key="teacher_validation_scorability_T001-D006").value is None
    assert any(button.label == "Save & Next" for button in app.button)
    assert not any(element.label == "VAD threshold" for element in app.selectbox)
    video.set_value("T001-D064").run()
    assert not app.exception
    assert not any(element.key == "teacher_validation_scorability_T001-D064"
                   for element in app.selectbox)


def test_validation_launcher_targets_separate_mode():
    batch = Path("START_VALIDATION_RATING.bat").read_text(encoding="utf-8")
    launcher = Path("scripts/start_validation_rating.ps1").read_text(encoding="utf-8")
    original = Path("scripts/start_teacher_rating.ps1").read_text(encoding="utf-8")
    assert "start_validation_rating.ps1" in batch
    assert "?mode=teacher_validation" in launcher
    assert "?mode=teacher" in original
    assert "teacher_validation" not in original
