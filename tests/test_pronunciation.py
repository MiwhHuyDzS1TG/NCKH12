import json
from pathlib import Path

import jsonschema
import pytest

from speaking_evidence.p22 import RATING_IDS, save_rating
from speaking_evidence.pronunciation import (
    OPENPRONOUNCE_VERSION,
    RATING_SCHEMA_VERSION,
    align_target_for_pronunciation,
    build_asr_pronunciation_baseline,
    calibrate_pronunciation_rows,
    create_rating_schema_v2,
    eligible_runs,
    probe_openpronounce,
    pronunciation_calibration_readiness,
    pronunciation_intelligibility_relationship,
    validate_pronunciation_input,
)


def _v1_rating(pair_id="T001-D005"):
    return {"pair_id": pair_id, "quality_gate": "GREEN", "amber_scorability": "NOT_REQUIRED",
            "fluency": None, "intelligibility": None, "prosody": None, "note": "",
            "human_confirmed": False, "rated_at_utc": None,
            "raw_evidence_ref": f"pairs/{pair_id}/raw_evidence.json"}


def test_rating_schema_v2_adds_null_pronunciation_without_overwriting_v1(tmp_path):
    source = tmp_path / "ratings_v1.json"
    source.write_text(json.dumps({"version": "v1", "rubric_version": "old", "items": [_v1_rating()],
                                  "holdout_used": False}), encoding="utf-8")
    before = source.read_bytes()
    destination = tmp_path / "ratings_v2.json"
    payload = create_rating_schema_v2(source, destination)
    assert source.read_bytes() == before
    assert payload["schema_version"] == RATING_SCHEMA_VERSION
    assert payload["criteria"] == ["fluency", "pronunciation", "intelligibility", "prosody"]
    assert payload["items"][0]["pronunciation"] is None
    assert payload["items"][0]["pronunciation_examples"] == ""
    assert payload["items"][0]["human_confirmed"] is False
    assert payload["provenance"]["source_preserved"] is True


def test_scorable_rating_requires_integer_pronunciation_and_preserves_edit_history(tmp_path):
    path = tmp_path / "ratings_v2.json"
    item = {**_v1_rating(), "pronunciation": None, "pronunciation_examples": ""}
    path.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    common = {"fluency": 3, "intelligibility": 3, "prosody": 3}
    with pytest.raises(ValueError, match="four ratings"):
        save_rating(path, item["pair_id"], "SCORABLE", common, "", True)
    with pytest.raises(ValueError, match="integers"):
        save_rating(path, item["pair_id"], "SCORABLE", {**common, "pronunciation": 3.5}, "", True)
    saved = save_rating(path, item["pair_id"], "SCORABLE", {**common, "pronunciation": 4}, "", True,
                        pronunciation_examples="worked, three")
    assert saved["pronunciation"] == 4
    assert saved["pronunciation_examples"] == "worked, three"
    save_rating(path, item["pair_id"], "SCORABLE", {**common, "pronunciation": 3}, "recheck", True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["history"][0]["previous_rating"]["pronunciation"] == 4


def test_alignment_excludes_omissions_and_uncertain_substitutions_from_pronunciation():
    words = [
        {"text": "one", "start_sec": 1.0, "end_sec": 1.2, "probability": .9},
        {"text": "tree", "start_sec": 1.3, "end_sec": 1.6, "probability": .7},
        {"text": "extra", "start_sec": 1.7, "end_sec": 1.9, "probability": .6},
        {"text": "four", "start_sec": 2.0, "end_sec": 2.2, "probability": .95},
    ]
    result = align_target_for_pronunciation("one two three four five", words)
    by_word = {row["target_word"]: row for row in result["target_words"]}
    assert by_word["one"]["status"] == "MATCHED" and by_word["one"]["eligible_for_pronunciation"]
    assert by_word["two"]["status"] in {"OMITTED", "SUBSTITUTED_OR_UNCERTAIN"}
    assert by_word["three"]["status"] in {"OMITTED", "SUBSTITUTED_OR_UNCERTAIN"}
    assert not by_word["two"]["eligible_for_pronunciation"]
    assert not by_word["three"]["eligible_for_pronunciation"]
    assert by_word["five"]["status"] == "OMITTED"
    assert by_word["five"]["handled_by"] == "ASR-assisted Reading Completeness"
    assert by_word["five"]["double_penalty_guard"] == "NO_PRONUNCIATION_ANALYSIS"
    assert all(row["pronunciation_error_confirmed"] is False for row in result["target_words"])
    run_words = sum(run["word_count"] for run in eligible_runs(result))
    assert run_words == result["status_counts"]["MATCHED"]


def _evidence(pair_id: str, model_ref: str) -> dict:
    return {"version": "test", "pair_id": pair_id, "scope": "DEVELOPMENT_ONLY", "holdout": False,
            "audio_provenance": {"canonical_source": "RAW_COMPLETED_DUET", "holdout": False,
                                 "model_input_ref": model_ref},
            "asr_provenance": {"backend": "faster_whisper", "model": "small.en", "version": "1.2.1"},
            "turns": [{"start_sec": 0.0, "end_sec": 3.0,
                       "transcript": {"runtime_sec": .1, "words": [
                           {"text": "one", "start_sec": .5, "end_sec": .8, "probability": .9},
                           {"text": "three", "start_sec": 1.2, "end_sec": 1.6, "probability": .5}],
                                      "verbatim_transcript": "one three"}}]}


def test_raw_duet_invariant_and_holdout_rejection(tmp_path):
    root = tmp_path / "evidence"
    pair = "T001-D005"
    audio = root / "pairs" / pair / "raw_learner_audio.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"raw-derived-audio")
    path = audio.parent / "evidence.json"
    good = _evidence(pair, f"pairs/{pair}/raw_learner_audio.wav")
    path.write_text(json.dumps(good), encoding="utf-8")
    assert validate_pronunciation_input(good, path, root) == audio
    residual = audio.parent / "residual_detection.wav"
    residual.write_bytes(b"forbidden")
    bad = _evidence(pair, f"pairs/{pair}/residual_detection.wav")
    with pytest.raises(ValueError, match="Detection/cancellation|Residual/cancelled"):
        validate_pronunciation_input(bad, path, root)
    holdout = _evidence("T001-D001", f"pairs/{pair}/raw_learner_audio.wav")
    with pytest.raises(ValueError, match="development"):
        validate_pronunciation_input(holdout, path, root)


def test_asr_baseline_is_deterministic_schema_valid_and_not_a_pronunciation_score(tmp_path):
    root = tmp_path / "evidence"
    for pair_id in RATING_IDS:
        pair_dir = root / "pairs" / pair_id
        pair_dir.mkdir(parents=True)
        (pair_dir / "raw_learner_audio.wav").write_bytes(b"raw-derived-audio")
        (pair_dir / "evidence.json").write_text(
            json.dumps(_evidence(pair_id, f"pairs/{pair_id}/raw_learner_audio.wav")), encoding="utf-8")
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"human_confirmed": True, "confirmed_text": "one two three"}),
                      encoding="utf-8")
    first = build_asr_pronunciation_baseline(root, target)
    artifact = root / "pairs" / RATING_IDS[0] / "pronunciation_asr_baseline_v1.json"
    first_bytes = artifact.read_bytes()
    second = build_asr_pronunciation_baseline(root, target)
    assert first == second and artifact.read_bytes() == first_bytes
    record = json.loads(first_bytes)
    schema = json.loads((Path(__file__).parents[1] / "speaking_evidence" / "schemas" /
                         "pronunciation_evidence_v1.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(record, schema)
    assert record["human_calibrated_score"] is None
    assert record["backend"]["role"].endswith("NOT_TRUE_PRONUNCIATION")
    assert all(not word["pronunciation_error_confirmed"] for word in record["word_evidence"])
    assert first["holdout_processed"] is False and first["human_ratings_used"] == 0


def test_benchmark_plan_is_frozen_versioned_and_keeps_constructs_separate():
    path = Path(__file__).parents[1] / "speaking_evidence" / "specs" / "pronunciation_benchmark_plan_v1.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    assert plan["version"] == "pronunciation-benchmark-plan-v1"
    assert plan["frozen_before_human_pronunciation_labels"] is True
    assert plan["holdout_allowed"] is False
    assert plan["canonical_audio_invariant"]["source"] == "RAW_COMPLETED_DUET"
    assert plan["construct_separation"]["keep_separate_until_human_relationship_is_measured"] is True
    openpronounce = next(item for item in plan["candidates"] if item["id"] == "CANDIDATE_B_OPENPRONOUNCE")
    assert openpronounce["package"] == f"openpronounce=={OPENPRONOUNCE_VERSION}"
    assert next(item for item in plan["candidates"] if item["id"] == "CANDIDATE_D_GOPT")[
        "selected_for_competition_mvp"] is False


def test_optional_backend_failure_is_nonfatal(tmp_path):
    result = probe_openpronounce(tmp_path, timeout_sec=.1)
    assert result["status"] in {"OPTIONAL_DEPENDENCY_MISSING", "BLOCKED_ESPEAK_NG_MISSING"}


def test_pronunciation_calibration_gate_and_metrics_are_prepared():
    waiting_rows = [{"pair_id": pair_id, "human_confirmed": False,
                     "amber_scorability": "NOT_REQUIRED", "pronunciation": None}
                    for pair_id in RATING_IDS]
    assert pronunciation_calibration_readiness(waiting_rows)["status"] == "WAITING_FOR_HUMAN_CALIBRATION"
    result = calibrate_pronunciation_rows(waiting_rows, ("machine",))
    assert result["scores"] == [] and result["holdout_processed"] is False
    ready_rows = [{"pair_id": pair_id, "human_confirmed": True,
                   "amber_scorability": "NOT_REQUIRED", "pronunciation": index % 3 + 2,
                   "machine": float(index)} for index, pair_id in enumerate(RATING_IDS[:9])]
    calibrated = calibrate_pronunciation_rows(ready_rows, ("machine",))
    mapping = calibrated["mapping"]
    assert mapping["validation"] == "LEAVE_ONE_OUT"
    assert "loo_mae" in mapping and "within_one_band_agreement" in mapping
    assert "spearman_correlation" in mapping and "quadratic_weighted_kappa" in mapping
    assert len(mapping["predicted_vs_human"]) == 9
    relationship = pronunciation_intelligibility_relationship(waiting_rows)
    assert relationship["status"] == "WAITING_FOR_HUMAN_CALIBRATION"
    assert relationship["spearman_correlation"] is None
