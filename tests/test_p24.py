import json
import subprocess
from pathlib import Path

import pytest

from speaking_evidence.p24 import (
    RATING_IDS,
    VALIDATION_IDS,
    _attach_mapping_diagnostics,
    load_frozen_plan,
    normalized_edit_distance,
    select_binary_candidate,
    write_winner_freeze,
)


def _plan() -> dict:
    return {
        "status": "FROZEN_BEFORE_CANDIDATE_BENCHMARK",
        "data_policy": {
            "calibration_model_selection_set": list(RATING_IDS),
            "development_model_validation_set": list(VALIDATION_IDS),
        },
    }


def test_frozen_plan_change_is_detected_after_results_exist(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(_plan()), encoding="utf-8")
    _, digest = load_frozen_plan(path)
    result = tmp_path / "result.json"
    result.write_text(json.dumps({"plan_sha256": digest}), encoding="utf-8")
    load_frozen_plan(path, result)
    changed = _plan(); changed["new_candidate"] = "post-hoc"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        load_frozen_plan(path, result)


def test_normalized_asr_disagreement_is_symmetric_and_not_error_label():
    assert normalized_edit_distance("one two three", "one too three") == pytest.approx(1 / 3)
    assert normalized_edit_distance("one too three", "one two three") == pytest.approx(1 / 3)
    assert normalized_edit_distance("same", "same") == 0


def test_majority_collapsed_intelligibility_challenger_cannot_be_promoted():
    mappings = {
        "I0": {"status": "MACHINE_CALIBRATION_UNSTABLE", "loo_mae": .30,
               "balanced_accuracy": .50, "majority_class_collapse": True},
        "I1": {"status": "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED", "loo_mae": .20,
               "balanced_accuracy": .90, "majority_class_collapse": True},
    }
    selected = select_binary_candidate({}, "I0", mappings, intelligibility=True)
    assert selected["selected"] == "I0"


def test_candidate_failure_does_not_replace_baseline():
    mappings = {
        "BASE": {"status": "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED", "loo_mae": .4,
                 "balanced_accuracy": .6},
        "FAILED": {"status": "BACKEND_UNAVAILABLE"},
    }
    assert select_binary_candidate({}, "BASE", mappings)["selected"] == "BASE"


def test_winner_freeze_cannot_consume_future_validation_ratings(tmp_path):
    result = write_winner_freeze(tmp_path / "winners.json", "abc", {
        "fluency": {"selected": "F0", "status": "BASELINE_RETAINED"}
    })
    assert result["development_validation_ids"] == list(VALIDATION_IDS)
    assert result["validation_human_ratings_read"] is False
    assert result["validation_runs_allowed"] == 1
    assert result["holdout_processed"] is False


def test_plan_distinguishes_embeddings_from_direct_scores():
    plan = json.loads(Path("pretrained_model_tournament_v1.json").read_text(encoding="utf-8"))
    executable = [candidate for candidate in plan["candidates"]["apa"]
                  if candidate["candidate_id"] != "APA_2_HUBERT_XLARGE_LS960_FT_CTC"]
    assert all("EMBEDDING_FEATURE" in candidate["output_type"] for candidate in executable)
    assert all(candidate["direct_pretrained_score_available"] is False for candidate in executable)
    assert plan["selection_policy"]["overall_score_allowed"] is False
    assert set(plan["prohibited_claims"]) >= {"CEFR", "B2", "IELTS"}


def test_model_weights_and_private_media_are_not_tracked():
    completed = subprocess.run(["git", "-c",
        "safe.directory=C:/Users/noobm/OneDrive/Máy tính/nckh12", "ls-files"],
        capture_output=True, text=True, check=True)
    tracked = completed.stdout.replace("\\", "/").splitlines()
    forbidden_suffixes = (".safetensors", ".bin", ".pt", ".wav", ".mp4", ".mov")
    assert not any(path.lower().endswith(forbidden_suffixes) for path in tracked)
    assert not any(path.startswith(("data/", "human_ground_truth/", "assessment_runs/"))
                   for path in tracked)


def test_feature_to_sample_ratio_is_explicitly_flagged():
    result = _attach_mapping_diagnostics({
        "features": ["a", "b", "c", "d"], "loo_predictions": [1.0, 2.0]
    }, runtime_sec=1.0)
    assert result["feature_count"] == 4
    assert result["model_selection_sample_size"] == 12
    assert result["supervised_feature_to_n_ratio"] == pytest.approx(1 / 3)
    assert result["feature_ratio_warning"] == "METHODOLOGICALLY_UNSAFE_FEATURE_TO_N_RATIO"
