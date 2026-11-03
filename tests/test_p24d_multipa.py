import json
from pathlib import Path

import pytest

from speaking_evidence.p24d_multipa import (
    MAX_CHUNK_SEC,
    RATED_IDS,
    RESERVED_IDS,
    aggregate_video,
    apply_fitted_mapping,
    fallback_decision,
    segment_closed_response,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "p24d_multipa_plan_v1.json").read_text(encoding="utf-8"))


def test_plan_uses_released_pretrained_multipa_in_isolated_environment_only():
    candidate = PLAN["candidate"]
    assert candidate["github_commit"] == "a8d83ec1d80f9db60e6d32227cb1c562ee5e6022"
    assert candidate["huggingface_revision"] == "ff1e3c79bfb1d113d887a0b7b05fe2900c095264"
    assert candidate["pretrained_only"] is True
    assert candidate["nckh12_neural_training_or_finetuning"] is False
    runner = (ROOT / "scripts/run_p24d_multipa.py").read_text(encoding="utf-8")
    assert '.local/multipa' in runner
    assert "PRETRAINED_INFERENCE_ONLY" in runner


def test_closed_response_segmentation_is_deterministic_and_never_invents_target_words():
    target = "one memorable event in my life happened at school"
    words = [
        {"text": word, "start_sec": i * 1.1, "end_sec": i * 1.1 + 0.7}
        for i, word in enumerate(target.split())
    ]
    first = segment_closed_response(words, target, maximum_sec=3.0)
    second = segment_closed_response(words, target, maximum_sec=3.0)
    assert first == second
    assert all(row["duration_sec"] <= 3.0 for row in first)
    assert all(row["target_text"] in target for row in first)
    assert all(row["valid_for_scoring"] for row in first)


def test_segment_limit_is_below_official_fifteen_second_boundary():
    assert MAX_CHUNK_SEC < 15.0
    assert PLAN["segmentation"]["aggregation"] == "UNWEIGHTED_MEAN_OF_ALL_VALID_CHUNKS"


def test_raw_completed_duet_and_holdout_invariants_are_frozen():
    assert PLAN["audio_policy"]["canonical_source"] == "RAW_COMPLETED_DUET"
    assert PLAN["audio_policy"]["cancellation_or_residual_allowed"] is False
    split = json.loads((ROOT / "cohort_runs/T001_p14/data_split_v2.json").read_text(encoding="utf-8"))
    assert set(RATED_IDS).isdisjoint(split["holdout"])
    assert set(RESERVED_IDS).isdisjoint(split["holdout"])
    assert PLAN["holdout_processed"] is False


def test_original_ratings_and_p24_freeze_are_hash_guarded():
    frozen = PLAN["frozen_inputs"]
    assert frozen["teacher_ratings_sha256"] == "6ffc1be2661c8ef3fbcf084c2cb4f83cec175d9f1996f20a444cdc6e13005f62"
    assert frozen["p24_winner_freeze_sha256"] == "caad327b1ef6881cc9273dc72bb8c34ab53faf67dd0ed8cde2e21ee5b024a7c6"
    assert PLAN["validation_human_ratings_read"] is False
    assert sha256_file(ROOT / "human_ground_truth/p22a_v1/ratings_v2.json") == frozen["teacher_ratings_sha256"]
    assert sha256_file(ROOT / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json") == frozen["p24_winner_freeze_sha256"]


def test_invalid_chunk_prevents_video_score_instead_of_fabricating_one():
    rows = [
        {"valid": True, "accuracy": 5.0, "fluency": 5.0, "prosody": 5.0,
         "total": 5.0, "runtime_sec": 1.0},
        {"valid": False, "error": "forced failure", "runtime_sec": 0.5},
    ]
    result = aggregate_video(rows, expected_chunks=2)
    assert result["valid"] is False
    assert result["raw_pretrained_score"] is None
    assert result["failure_reasons"] == ["forced failure"]
    fallback = fallback_decision(valid_videos=9)
    assert fallback["oollim_evaluation_allowed"] is True
    assert fallback["oollim_autorun"] is False


def test_raw_and_calibrated_scores_are_explicitly_distinct_and_support_clipped():
    mapping = {
        "status": "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED",
        "model": "ridge_regularized_binary_logistic_expected_score",
        "features": ["multipa_accuracy"],
        "feature_mean": [5.0], "feature_scale": [1.0],
        "intercept": 0.0, "coefficients": [1.0], "observed_support": [3, 4],
    }
    calibrated = apply_fitted_mapping(mapping, "multipa_accuracy", 8.0)
    assert 3 <= calibrated <= 4
    assert PLAN["score_policy"]["raw_and_calibrated_labels_distinct"] is True


def test_no_unsupported_intelligibility_or_overall_score_is_defined():
    selection = PLAN["selection_policy"]
    assert selection["intelligibility"] == "HUMAN_ONLY_MACHINE_UNSTABLE"
    assert selection["overall_score"] is None
    with pytest.raises(ValueError):
        apply_fitted_mapping({
            "status": "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED",
            "model": "ridge_regularized_binary_logistic_expected_score",
            "features": ["other"], "feature_mean": [0], "feature_scale": [1],
            "intercept": 0, "coefficients": [0], "observed_support": [3, 4],
        }, "intelligibility", 1.0)


def test_demo_cache_contract_requires_input_and_model_hashes():
    runner = (ROOT / "scripts/run_p24d_multipa.py").read_text(encoding="utf-8")
    assert '"input_hash"' in runner
    assert '"model_sha256"' in runner
    assert '"fake_or_placeholder_score": False' in runner
