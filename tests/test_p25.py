import inspect
import json
from pathlib import Path

import pytest

from speaking_evidence.p24d_multipa import sha256_file
from speaking_evidence.p25 import (
    ORIGINAL_RATINGS_PATH,
    PLAN_NAME,
    RATINGS_PATH,
    VALIDATION_IDS,
    create_frozen_predictions,
    evaluate_frozen_predictions,
    verify_frozen_plan,
)


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local/multipa/p25/run"
PLAN = json.loads((ROOT / PLAN_NAME).read_text(encoding="utf-8"))
PRIVATE_RESULTS = all((LOCAL / name).is_file() for name in (
    "frozen_predictions.json", "p25_evaluation.json"
))
PRIVATE_FROZEN_INPUTS = all((ROOT / name).is_file() for name in (
    RATINGS_PATH,
    ORIGINAL_RATINGS_PATH,
    ".local/multipa/run/p24d_summary.json",
    "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json",
))


def test_p25_plan_freezes_exact_development_membership_and_scorer_inputs():
    assert VALIDATION_IDS == ("T001-D064", "T001-D043", "T001-D048")
    assert tuple(PLAN["validation_ids"]) == VALIDATION_IDS
    split = json.loads(
        (ROOT / "cohort_runs/T001_p14/data_split_v2.json").read_text(encoding="utf-8")
    )
    assert set(VALIDATION_IDS) <= set(split["development"])
    assert set(VALIDATION_IDS).isdisjoint(split["holdout"])
    assert PLAN["holdout_processed"] is False
    assert PLAN["p24d_pre_rating_summary_sha256"] == (
        "0cc9a12292fe100e8cf96240b8fcf7ec193bd23919144a22367bdb556240a812"
    )
    assert PLAN["p24d_plan_sha256"] == (
        "90755aaa169b605c7b9a070ae411dc28366a2b3e568e4daf2e81dc15a4cee1c1"
    )
    assert PLAN["p24d_report_sha256"] == (
        "b7824a624a8197db59f297e9f328bb0fdcb2d3400c4e4ae323bf6838786deecb"
    )


@pytest.mark.skipif(not PRIVATE_FROZEN_INPUTS, reason="private frozen inputs are not distributed")
def test_p25_hash_guard_verifies_the_local_frozen_inputs():
    verify_frozen_plan(ROOT, PLAN, include_ratings=True)


def test_p25_prediction_stage_cannot_read_ratings_or_fit_models():
    source = inspect.getsource(create_frozen_predictions)
    assert "RATINGS_PATH" not in source
    assert "fit(" not in source
    assert "train(" not in source
    assert "calibrat" not in source.lower()
    assert PLAN["prediction_stage_reads_validation_ratings"] is False
    assert PLAN["training_or_refitting_allowed"] is False
    assert PLAN["threshold_or_feature_change_allowed"] is False
    assert PLAN["model_reselection_allowed"] is False


def test_p25_unsupported_scores_are_absent():
    assert PLAN["criteria"]["intelligibility"]["machine_score"] is None
    assert PLAN["criteria"]["overall"] is None
    assert "apply_fitted_mapping" not in inspect.getsource(evaluate_frozen_predictions)


@pytest.mark.skipif(not PRIVATE_FROZEN_INPUTS, reason="private frozen inputs are not distributed")
def test_p25_preserves_human_artifacts():
    assert sha256_file(ROOT / ORIGINAL_RATINGS_PATH) == (
        "6ffc1be2661c8ef3fbcf084c2cb4f83cec175d9f1996f20a444cdc6e13005f62"
    )
    assert sha256_file(ROOT / RATINGS_PATH) == (
        "707d4c33eafaaf54a21c131bff6b1fec09538b06d911b447275fd69ef00ed464"
    )


@pytest.mark.skipif(not PRIVATE_RESULTS, reason="local frozen P2.5 run is not distributed")
def test_p25_run_evaluates_exactly_three_without_leakage_or_holdout():
    predictions = json.loads((LOCAL / "frozen_predictions.json").read_text(encoding="utf-8"))
    evaluation = json.loads((LOCAL / "p25_evaluation.json").read_text(encoding="utf-8"))
    assert tuple(predictions["validation_ids"]) == VALIDATION_IDS
    assert tuple(row["pair_id"] for row in predictions["predictions"]) == VALIDATION_IDS
    assert predictions["validation_ratings_read"] is False
    assert predictions["training_or_refitting_performed"] is False
    assert predictions["machine_intelligibility_score"] is None
    assert predictions["overall_score"] is None
    assert predictions["holdout_processed"] is False
    assert tuple(row["pair_id"] for row in evaluation["rows"]) == VALIDATION_IDS
    assert evaluation["validation_ratings_used_for_fitting"] is False
    assert evaluation["scorer_changed_after_ratings"] is False
    assert evaluation["intelligibility"] == "HUMAN_ONLY / MACHINE_UNSTABLE"
    assert evaluation["overall"] is None
    assert evaluation["holdout_processed"] is False


@pytest.mark.skipif(not PRIVATE_RESULTS, reason="local frozen P2.5 run is not distributed")
def test_p25_report_exposes_every_case_and_small_sample_warning():
    report = (ROOT / "P25_FROZEN_MINI_VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for pair_id in ("D064", "D043", "D048"):
        assert report.count(f"| {pair_id} |") >= 3
    assert "N=3" in report
    assert "descriptive only" in report
    assert "HUMAN_ONLY / MACHINE_UNSTABLE" in report
    assert "Overall:** not created" in report
    assert "Fixed holdout processed: **NO**" in report
