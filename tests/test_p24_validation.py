import copy
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
    validate_validation_rating_artifact,
)
from speaking_evidence.p24_validation_correction import (
    FINAL_IDS as CORRECTED_FINAL_IDS,
    FORCED_EXCLUSIONS,
    MANIFEST_NAME as CORRECTED_MANIFEST_NAME,
    VERSION as CORRECTED_VERSION,
    build_corrected_manifest,
    validate_corrected_manifest,
)
from speaking_evidence.p24_validation_final import (
    EXCLUDED_IDS,
    FINAL_IDS,
    MANIFEST_NAME as FINAL_MANIFEST_NAME,
    MEMBERSHIP_SHA256,
    P24D_PLAN_SHA256,
    P24D_REPORT_SHA256,
    VERSION as FINAL_VERSION,
    queue_membership_sha256,
    validate_final_queue_manifest,
)
from speaking_evidence.p24_validation_preflight import (
    MANIFEST_NAME as V1_MANIFEST_NAME,
    ORIGINAL_IDS,
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
        "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json",
        "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json",
        "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json",
        "cohort_runs/T001_p14/data_split_v2.json",
        "cohort_runs/T001_p14/development_manifest_v3.json",
        V1_MANIFEST_NAME,
        CORRECTED_MANIFEST_NAME,
        FINAL_MANIFEST_NAME,
        "p24d_multipa_plan_v1.json",
        "MULTIPA_COMPETITION_SCORER_REPORT.md",
    )
    for relative in copies:
        source, destination = Path(relative), tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    summary_path = tmp_path / "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for item in summary["items"]:
        audio = tmp_path / "assessment_runs/T001_p24_tournament_v1" / item["model_input_ref"]
        audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16_000)
            handle.writeframes(b"\x00\x00" * 160)
        item["model_input_sha256"] = _sha(audio)
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    artifact = tmp_path / "human_ground_truth/p24_validation_v1/development_validation_ratings_v2.json"
    return tmp_path, artifact


def test_corrected_queue_excludes_manual_failures_and_original_calibration_set():
    assert ORIGINAL_IDS == (
        "T001-D006", "T001-D023", "T001-D064", "T001-D043", "T001-D048"
    )
    assert FORCED_EXCLUSIONS == ("T001-D006", "T001-D023")
    assert VALIDATION_IDS == FINAL_IDS == CORRECTED_FINAL_IDS == (
        "T001-D064", "T001-D043", "T001-D048"
    )
    assert set(VALIDATION_IDS).isdisjoint(RATING_IDS)


def test_v3_final_queue_freezes_three_ids_hash_and_historical_exclusions():
    manifest = json.loads(Path(FINAL_MANIFEST_NAME).read_text(encoding="utf-8"))
    validate_final_queue_manifest(manifest)
    assert manifest["version"] == FINAL_VERSION
    assert tuple(manifest["final_queue_ids"]) == FINAL_IDS
    assert tuple(manifest["excluded_ids"]) == EXCLUDED_IDS
    assert manifest["queue_membership_sha256"] == MEMBERSHIP_SHA256
    assert queue_membership_sha256(list(FINAL_IDS)) == MEMBERSHIP_SHA256
    assert manifest["validation_progress"] == "0/3"
    assert manifest["replacement_status"] == (
        "NO_REPLACEMENTS_AVAILABLE_ELIGIBLE_DEVELOPMENT_POOL_EXHAUSTED"
    )
    for exclusion in manifest["technical_exclusions"]:
        assert exclusion["decision"] == "NOT_SCORABLE / EXCLUDE_FROM_VALIDATION"
        assert exclusion["reason"] == "PRE_RATING_TECHNICAL_ELIGIBILITY_EXCLUSION"
        assert exclusion["replacement"] is None


def test_v1_backup_ranking_was_frozen_empty_before_manual_correction():
    manifest = json.loads(Path(V1_MANIFEST_NAME).read_text(encoding="utf-8"))
    validate_replacement_manifest(manifest)
    assert manifest["ratings_before_audit"] == "0/5"
    assert manifest["deterministic_backup_ranking"] == []
    assert manifest["eligible_replacement_pool"] == []
    assert manifest["selection_uses_human_validation_scores"] is False
    assert manifest["split_proof"]["final_holdout_intersection"] == []


def test_corrected_manifest_preserves_exact_p1_reasons_and_does_not_lower_threshold():
    manifest = json.loads(Path(CORRECTED_MANIFEST_NAME).read_text(encoding="utf-8"))
    validate_corrected_manifest(manifest)
    assert manifest["version"] == CORRECTED_VERSION
    assert tuple(manifest["excluded_ids"]) == FORCED_EXCLUSIONS
    assert tuple(manifest["final_queue_ids"]) == FINAL_IDS
    assert manifest["deterministic_backup_ranking"] == []
    assert manifest["eligible_replacement_pool"] == []
    assert manifest["replacements"] == []
    assert manifest["replacement_pool_exhausted"] is True
    assert manifest["replacement_threshold_lowered"] is False
    assert manifest["selection_uses_teacher_ratings"] is False
    assert manifest["validation_progress"] == "0/5"
    assert manifest["five_item_queue_complete"] is False
    assert manifest["all_retained_items_scorable"] is True
    assert manifest["all_final_items_scorable"] is False
    assert manifest["split_proof"]["retained_holdout_intersection"] == []
    exclusions = {item["pair_id"]: item for item in manifest["technical_exclusions"]}
    for pair_id in FORCED_EXCLUSIONS:
        item = exclusions[pair_id]
        assert item["decision"] == "NOT_SCORABLE / EXCLUDE_FROM_VALIDATION"
        assert item["quality_gate_reason_codes"] == [
            "POSSIBLE_TRUE_OVERLAP", "UNUSUAL_DURATION"
        ]
        assert item["p1_scorability_reasons"] == [
            "Reference audio was reduced by a reliable cancellation backend"
        ]
        assert item["p1_audio_presence_reasons"] == [
            "Multiple aligned audio features indicate audible template speech"
        ]
        assert item["reference_contamination_scope"] == "SCORING_REGION"


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_correction_freezes_and_refuses_any_criterion_rating(tmp_path):
    root, _ = _private_fixture(tmp_path)
    artifact = root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    destination = root / "fresh_correction.json"
    first = build_corrected_manifest(root, destination)
    frozen_bytes = destination.read_bytes()
    assert build_corrected_manifest(root, destination) == first
    assert destination.read_bytes() == frozen_bytes
    destination.unlink()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["items"][0]["fluency"] = 4
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Criterion rating exists"):
        build_corrected_manifest(root, destination)


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_v3_artifact_initializes_three_null_items_at_zero_of_three(tmp_path):
    root, artifact = _private_fixture(tmp_path)
    original = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    winner = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_before, winner_before = original.read_bytes(), winner.read_bytes()
    payload = initialize_validation_rating_artifact(root, artifact)
    assert tuple(payload["queue_ids"]) == FINAL_IDS
    assert payload["rating_schema_version"] == RATING_SCHEMA_VERSION
    assert payload["status"] == "READY_FOR_TEACHER_RATING"
    assert payload["target_count"] == 3
    assert payload["completed_count"] == 0 and payload["pending_count"] == 3
    assert payload["queue_membership_sha256"] == MEMBERSHIP_SHA256
    assert rating_progress(payload) == (0, 3)
    assert all(item["human_confirmed"] is False for item in payload["items"])
    assert all(item["amber_scorability"] is None for item in payload["items"])
    assert all(item[label] is None for item in payload["items"]
               for label in ("fluency", "pronunciation", "intelligibility", "prosody"))
    assert payload["ratings_must_not_reselect_or_refit_scorer"] is True
    assert payload["automatic_calibration"] is False
    assert payload["automatic_p25"] is False
    assert original.read_bytes() == original_before
    assert winner.read_bytes() == winner_before


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_v3_queue_persists_fixture_rating_and_rejects_membership_tampering(tmp_path):
    root, artifact = _private_fixture(tmp_path)
    initialize_validation_rating_artifact(root, artifact)
    original = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    winner = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_hash, winner_hash = _sha(original), _sha(winner)
    save_validation_rating(
        artifact, root, "T001-D064", "SCORABLE",
        {"fluency": 2, "pronunciation": 3, "intelligibility": 4, "prosody": 5},
    )
    restarted = json.loads(artifact.read_text(encoding="utf-8"))
    assert rating_progress(restarted) == (1, 3)
    assert next(item for item in restarted["items"] if item["pair_id"] == "T001-D064")["fluency"] == 2
    tampered = copy.deepcopy(restarted)
    tampered["items"][0]["pair_id"] = "T001-D006"
    with pytest.raises(ValueError, match="membership"):
        validate_validation_rating_artifact(tampered)
    assert _sha(original) == original_hash == ORIGINAL_RATINGS_SHA256
    assert _sha(winner) == winner_hash
    assert not (root / "assessment_runs/T001_p25_frozen_validation_v1").exists()


@pytest.mark.skipif(not PRIVATE_REQUIRED, reason="private workflow artifacts are not distributed")
def test_teacher_validation_ui_is_unblocked_ordered_and_hides_machine_evidence():
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60)
    app.query_params["mode"] = "teacher_validation"
    app.run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.title, app.caption, app.markdown, app.info, app.warning, app.error)
                        for element in group)
    ratings = json.loads(Path(
        "human_ground_truth/p24_validation_v1/development_validation_ratings_v2.json"
    ).read_text(encoding="utf-8"))
    completed, total = rating_progress(ratings)
    assert f"Development Validation: {completed} / {total}" in rendered
    assert "VALIDATION QUEUE BLOCKED" not in rendered
    selector = next(element for element in app.selectbox
                    if element.key == "teacher_validation_pair")
    assert tuple(str(option).split()[0] for option in selector.options) == FINAL_IDS
    assert any(button.label == "Save & Next" for button in app.button)
    assert all(pair_id not in rendered for pair_id in EXCLUDED_IDS)
    assert all(term not in rendered.lower() for term in (
        "f0_baseline", "p0_asr_recognition", "i0_single_asr", "r0_praat",
        "micro-wer", "asr confidence", "pretrained_embedding_feature",
        "machine_calibration_unstable",
    ))


def test_validation_launcher_targets_separate_three_item_mode():
    batch = Path("START_VALIDATION_RATING.bat").read_text(encoding="utf-8")
    launcher = Path("scripts/start_validation_rating.ps1").read_text(encoding="utf-8")
    original = Path("scripts/start_teacher_rating.ps1").read_text(encoding="utf-8")
    assert "start_validation_rating.ps1" in batch
    assert "?mode=teacher_validation" in launcher
    assert "?mode=teacher" in original
    assert "teacher_validation" not in original


def test_frozen_hash_constants_are_unchanged():
    assert PLAN_SHA256 == "28b2e4ef7c17214c202e09bcc1a5c01c7cecc309a81881c86dec21b81886836a"
    assert ORIGINAL_RATINGS_SHA256 == "6ffc1be2661c8ef3fbcf084c2cb4f83cec175d9f1996f20a444cdc6e13005f62"
    assert _sha(Path("p24d_multipa_plan_v1.json")) == P24D_PLAN_SHA256
    assert _sha(Path("MULTIPA_COMPETITION_SCORER_REPORT.md")) == P24D_REPORT_SHA256
