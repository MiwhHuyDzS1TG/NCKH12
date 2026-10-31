import copy
import json
from pathlib import Path

import jsonschema
import pytest

from speaking_evidence.feedback_contract import (
    CRITERIA,
    build_feedback_contract,
    validate_feedback_contract,
)
from speaking_evidence.p22 import DISCLAIMER


def _evidence():
    return {
        "pair_id": "T001-D005",
        "scope": "DEVELOPMENT_ONLY",
        "holdout": False,
        "audio_provenance": {"canonical_source": "RAW_COMPLETED_DUET"},
        "aggregate_fluency_evidence": {"pause_ratio": .2, "long_pause_count": 2,
            "longest_pause_sec": 1.1, "mean_length_of_run_words": 5.0,
            "speech_rate_wpm": 150.0, "articulation_rate_wpm": 180.0,
            "phonation_ratio": .8},
        "turns": [{"transcript": {"words": [{"text": "one", "probability": .9}]},
                   "acoustic": {"f0_range_semitones": 8.0, "f0_std_semitones": 2.0,
                                "intensity_std_db": 4.0, "voiced_fraction": .7}}],
    }


def test_feedback_contract_waiting_state_has_no_invented_scores_or_feedback():
    contract = build_feedback_contract(
        _evidence(),
        {"status": "EVIDENCE_READY_NO_SCORE", "coverage": .9,
         "matched_sequence": [{}] * 9, "omissions": [{}], "insertions": [],
         "warning": "ASR differences are not proven learner errors"},
    )
    assert contract["status"] == "WAITING_FOR_HUMAN_CALIBRATION"
    assert set(contract["criteria"]) == set(CRITERIA)
    assert all(item["score"] is None for item in contract["criteria"].values())
    assert contract["generation"]["status"] == "NOT_YET_GENERATED"
    assert contract["criteria"]["pronunciation"]["evidence"]["error_diagnoses_confirmed"] is False
    schema = json.loads((Path(__file__).parents[1] / "speaking_evidence" / "schemas" /
                         "feedback_input_v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(contract, schema)


def test_feedback_contract_accepts_only_saved_preliminary_calibration_scores():
    summary = {"labels": DISCLAIMER, "holdout_processed": False, "scores": [{
        "pair_id": "T001-D005", "fluency": 3.2, "pronunciation": None,
        "intelligibility": 3.4, "completeness": 4.5, "prosody": 3.0,
    }]}
    contract = build_feedback_contract(_evidence(), None, calibration_summary=summary)
    assert contract["criteria"]["fluency"]["score"] == 3.2
    assert contract["criteria"]["pronunciation"]["score"] is None
    tampered = copy.deepcopy(contract)
    tampered["status"] = "WAITING_FOR_HUMAN_CALIBRATION"
    with pytest.raises(ValueError, match="Uncalibrated"):
        validate_feedback_contract(tampered)


def test_feedback_contract_rejects_holdout_or_non_raw_evidence():
    holdout = _evidence(); holdout["holdout"] = True
    with pytest.raises(ValueError, match="development"):
        build_feedback_contract(holdout, None)
    residual = _evidence(); residual["audio_provenance"]["canonical_source"] = "RESIDUAL"
    with pytest.raises(ValueError, match="RAW_COMPLETED_DUET"):
        build_feedback_contract(residual, None)
