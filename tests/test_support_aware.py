import hashlib
import json
from pathlib import Path

import pytest

from speaking_evidence.p22 import apply_mapping, fit_support_aware_mapping
from speaking_evidence.support_aware import (
    audit_teacher_rating_audio,
    freeze_rating_snapshot,
    select_coverage_expansion,
)


def _binary_rows(high_count: int, total: int = 12) -> list[dict]:
    rows = []
    for index in range(total):
        rows.append({
            "pair_id": f"T001-D{index + 1:03d}",
            "rating": 5 if index < high_count else 4,
            "x": float(index),
            "z": float((index * 3) % 7),
        })
    return rows


def test_two_level_mapping_is_constrained_to_observed_support():
    mapping = fit_support_aware_mapping(_binary_rows(4), "rating", ("x", "z"))
    assert mapping["observed_support"] == [4, 5]
    assert mapping["output_constraint"] == [4, 5]
    assert all(4 <= row["predicted_expected_score"] <= 5
               for row in mapping["predicted_vs_human"])
    value = apply_mapping(mapping, {"x": 1000.0, "z": -1000.0})
    if value is not None:
        assert 4 <= value <= 5


def test_one_level_criterion_cannot_calibrate():
    rows = [{"pair_id": f"P{index}", "rating": 4, "x": float(index)}
            for index in range(12)]
    mapping = fit_support_aware_mapping(rows, "rating", ("x",))
    assert mapping["status"] == "EVIDENCE_ONLY_SINGLE_OBSERVED_LEVEL"
    assert mapping["learner_facing_score_allowed"] is False
    assert apply_mapping(mapping, {"x": 1.0}) is None


def test_severe_binary_imbalance_can_be_machine_unstable():
    mapping = fit_support_aware_mapping(_binary_rows(2), "rating", ("x", "z"))
    assert mapping["severe_imbalance"] is True
    assert mapping["status"] == "MACHINE_CALIBRATION_UNSTABLE"
    assert mapping["learner_facing_score_allowed"] is False
    assert apply_mapping(mapping, {"x": 2.0, "z": 3.0}) is None


def test_rating_freeze_is_byte_exact_and_adds_provenance_separately(tmp_path):
    ratings = {"schema_version": "P2.3-four-criterion-v2", "holdout_used": False,
               "items": [{"pair_id": "T001-D001", "human_confirmed": True,
                          "fluency": 4, "pronunciation": 3,
                          "intelligibility": 4, "prosody": 3}]}
    source = tmp_path / "ratings_v2.json"
    source.write_text(json.dumps(ratings, ensure_ascii=False, indent=2), encoding="utf-8")
    before = source.read_bytes()
    manifest = freeze_rating_snapshot(source, tmp_path / "frozen", {
        "teacher_rating_audio_source": "RAW_CROPPED"
    })
    assert source.read_bytes() == before
    assert manifest["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert manifest["snapshot_sha256"] == manifest["source_sha256"]
    assert manifest["raw_labels_modified"] is False
    assert manifest["rating_provenance"]["classification"] == "HUMAN_REVIEWED_AI_ASSISTED"


def test_audio_audit_detects_raw_cropped_contract(tmp_path):
    evidence_root = tmp_path / "assessment"
    pair = evidence_root / "pairs" / "T001-D001"
    pair.mkdir(parents=True)
    model = pair / "raw_learner_audio.wav"
    model.write_bytes(b"fixture")
    (pair / "raw_evidence.json").write_text(json.dumps({
        "pair_id": "T001-D001", "raw_duet_path": "data/duets/T001/a.mp4",
        "model_input_ref": "pairs/T001-D001/raw_learner_audio.wav",
    }), encoding="utf-8")
    (pair / "evidence.json").write_text(json.dumps({
        "audio_provenance": {"canonical_source": "RAW_COMPLETED_DUET"}
    }), encoding="utf-8")
    audit = audit_teacher_rating_audio(evidence_root, [{"pair_id": "T001-D001"}])
    assert audit["teacher_rating_audio_source"] == "RAW_CROPPED"
    assert audit["cancellation_or_residual_used"] is False


def test_audio_audit_does_not_misclassify_residual_as_raw(tmp_path):
    evidence_root = tmp_path / "assessment"
    pair = evidence_root / "pairs" / "T001-D001"
    pair.mkdir(parents=True)
    (pair / "residual_detection.wav").write_bytes(b"fixture")
    (pair / "raw_evidence.json").write_text(json.dumps({
        "pair_id": "T001-D001", "raw_duet_path": "data/duets/T001/a.mp4",
        "model_input_ref": "pairs/T001-D001/residual_detection.wav",
    }), encoding="utf-8")
    (pair / "evidence.json").write_text(json.dumps({
        "audio_provenance": {"canonical_source": "RESIDUAL_DETECTION"}
    }), encoding="utf-8")
    audit = audit_teacher_rating_audio(evidence_root, [{"pair_id": "T001-D001"}])
    assert audit["teacher_rating_audio_source"] == "UNKNOWN"
    assert audit["cancellation_or_residual_used"] is None


def test_expansion_selection_is_development_only_and_label_blind():
    existing = ("T001-D001",)
    rows = [{"pair_id": "T001-D001", "quality_gate": "GREEN",
             "scorability_status": "SCORABLE_CLEAN", "learner_duration_sec": 45,
             "scorability_confidence": .9, "reference_audio_presence_score": .1,
             "audio_quality_features": {"speech_to_background_db": 20,
                                        "speech_level_dbfs_median": -25}}]
    for index in range(2, 10):
        rows.append({"pair_id": f"T001-D{index:03d}", "quality_gate": "AMBER",
                     "scorability_status": "SCORABLE_CLEAN", "learner_duration_sec": 40 + index,
                     "scorability_confidence": .7, "reference_audio_presence_score": index / 100,
                     "audio_quality_features": {"speech_to_background_db": 10 + index,
                                                "speech_level_dbfs_median": -35 + index}})
    split = {"development": [row["pair_id"] for row in rows], "holdout": ["T001-H001"]}
    first = select_coverage_expansion(rows, split, existing, count=6)
    second = select_coverage_expansion(rows, split, existing, count=6)
    assert first["selected_ids"] == second["selected_ids"]
    assert len(first["selected_ids"]) == 6
    assert first["selection_uses_human_scores"] is False
    assert first["split_proof"]["selected_holdout_intersection"] == []
    assert all(item["human_score_used_for_selection"] is False for item in first["items"])


@pytest.mark.skipif(
    not Path("human_ground_truth/p22a_v1/frozen/p22c_v1/ratings_v2_frozen_p22c_manifest_v1.json").is_file(),
    reason="private frozen human-rating artifacts are not distributed",
)
def test_real_p22c_snapshot_preserves_all_twelve_labels_exactly():
    source = Path("human_ground_truth/p22a_v1/ratings_v2.json")
    frozen_root = Path("human_ground_truth/p22a_v1/frozen/p22c_v1")
    snapshot = frozen_root / "ratings_v2_frozen_p22c_v1.json"
    manifest = json.loads((frozen_root / "ratings_v2_frozen_p22c_manifest_v1.json").read_text(
        encoding="utf-8"))
    assert source.read_bytes() == snapshot.read_bytes()
    assert manifest["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["raw_labels_modified"] is False
    assert manifest["confirmed_count"] == 12
    assert manifest["observed_distributions"] == {
        "fluency": {"4": 8, "5": 4},
        "pronunciation": {"3": 5, "4": 7},
        "intelligibility": {"4": 10, "5": 2},
        "prosody": {"2": 1, "3": 7, "4": 3, "5": 1},
    }
