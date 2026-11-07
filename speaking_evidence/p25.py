"""Frozen P2.5 development mini-validation; prediction precedes rating access."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from speaking_evidence.fluency import measure_fluency
from speaking_evidence.p22 import align_completeness, apply_mapping
from speaking_evidence.p24d_multipa import (
    aggregate_video,
    apply_fitted_mapping,
    correlation,
    segment_closed_response,
    sha256_file,
    write_wav_slice,
)


VERSION = "P2.5-frozen-development-mini-validation-v1"
VALIDATION_IDS = ("T001-D064", "T001-D043", "T001-D048")
PLAN_NAME = "p25_frozen_mini_validation_plan_v1.json"
RATINGS_PATH = "human_ground_truth/p24_validation_v1/development_validation_ratings_v2.json"
ORIGINAL_RATINGS_PATH = "human_ground_truth/p22a_v1/ratings_v2.json"
P24D_SUMMARY_PATH = ".local/multipa/run/p24d_summary.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def verify_frozen_plan(root: Path, plan: dict, include_ratings: bool) -> None:
    checks = {
        "queue_manifest_sha256": root / "p24_validation_final_queue_v3.json",
        "original_12_ratings_sha256": root / ORIGINAL_RATINGS_PATH,
        "split_sha256": root / "cohort_runs/T001_p14/data_split_v2.json",
        "target_text_sha256": root / "task_profiles/T001_target_text_v1.json",
        "validation_inputs_summary_sha256": root / "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json",
        "p24d_plan_sha256": root / "p24d_multipa_plan_v1.json",
        "p24d_report_sha256": root / "MULTIPA_COMPETITION_SCORER_REPORT.md",
        "p24d_pre_rating_summary_sha256": root / P24D_SUMMARY_PATH,
        "p24_criterion_summary_sha256": root / "assessment_runs/T001_p24_tournament_v1/criterion_tournament_summary.json",
    }
    if include_ratings:
        checks["validation_ratings_sha256"] = root / RATINGS_PATH
    for key, path in checks.items():
        if sha256_file(path) != plan[key]:
            raise ValueError(f"Frozen P2.5 input changed: {path}")
    if tuple(plan.get("validation_ids", [])) != VALIDATION_IDS:
        raise ValueError("P2.5 validation membership changed")
    if plan.get("prediction_stage_reads_validation_ratings") is not False:
        raise ValueError("Prediction stage must not read validation ratings")
    if any(plan.get(name) is not False for name in (
        "training_or_refitting_allowed", "threshold_or_feature_change_allowed",
        "model_reselection_allowed", "holdout_processed", "overall_score_created",
    )):
        raise ValueError("Frozen scorer/no-holdout policy changed")
    if plan["criteria"]["intelligibility"]["machine_score"] is not None:
        raise ValueError("P2.5 must not emit machine Intelligibility")
    if plan["criteria"]["overall"] is not None:
        raise ValueError("P2.5 must not create Overall")


def prepare_machine_request(root: Path, local_root: Path) -> dict:
    """Prepare all machine inputs without opening the validation rating artifact."""
    plan_path = root / PLAN_NAME
    plan = _load(plan_path)
    verify_frozen_plan(root, plan, include_ratings=False)
    split = _load(root / "cohort_runs/T001_p14/data_split_v2.json")
    if not set(VALIDATION_IDS) <= set(split["development"]) or set(VALIDATION_IDS) & set(split["holdout"]):
        raise ValueError("P2.5 IDs must be development-only")
    target = _load(root / "task_profiles/T001_target_text_v1.json")
    if target.get("human_confirmed") is not True:
        raise ValueError("P2.5 requires the frozen human-confirmed target")
    tournament = root / "assessment_runs/T001_p24_tournament_v1"
    summary = _load(tournament / "validation_inputs_summary.json")
    source_by_id = {item["pair_id"]: item for item in summary["items"]}
    items = []
    evidence_items = []
    for pair_id in VALIDATION_IDS:
        source = source_by_id[pair_id]
        provenance = _load(tournament / "validation_inputs" / pair_id / "input_provenance.json")
        audio = tournament / source["model_input_ref"]
        if (source.get("canonical_source") != "RAW_COMPLETED_DUET"
                or source.get("scorability_status") != "SCORABLE_CLEAN"
                or source.get("holdout") is not False
                or sha256_file(audio) != source["model_input_sha256"]):
            raise ValueError(f"{pair_id}: RAW_CROPPED/scorability invariant failed")
        asr_path = tournament / "asr/ASR_A_SMALL_EN" / f"{pair_id}.json"
        asr = _load(asr_path)
        if asr.get("input_sha256") != source["model_input_sha256"] or asr.get("error") is not None:
            raise ValueError(f"{pair_id}: frozen small.en evidence mismatch")
        timed_words = [{"text": word["text"], "start_sec": word["start"],
                        "end_sec": word["end"], "probability": word.get("probability")}
                       for word in asr["words"]]
        chunks = segment_closed_response(timed_words, target["confirmed_text"])
        if not chunks or not all(chunk["valid_for_scoring"] for chunk in chunks):
            raise ValueError(f"{pair_id}: unreliable target-aligned chunk")
        for chunk in chunks:
            destination = local_root / "chunks" / pair_id / f"chunk_{chunk['chunk_index']:02d}.wav"
            write_wav_slice(audio, destination, chunk["start_sec"], chunk["end_sec"])
            chunk["wav_path"] = str(destination.resolve())
            chunk["wav_sha256"] = sha256_file(destination)
        fluency = measure_fluency(provenance["turn"], timed_words)
        completeness = align_completeness(
            target["confirmed_text"], asr["transcript"], "ASR_A_SMALL_EN_FROZEN")
        items.append({"pair_id": pair_id, "chunks": chunks})
        evidence_items.append({
            "pair_id": pair_id,
            "canonical_source": source["canonical_source"],
            "audio_source_type": "RAW_CROPPED",
            "model_input_sha256": source["model_input_sha256"],
            "asr_evidence_sha256": sha256_file(asr_path),
            "fluency_features": fluency,
            "completeness": completeness,
            "chunk_count": len(chunks),
        })
    request = {
        "mode": "PRETRAINED_INFERENCE_ONLY",
        "plan_sha256": sha256_file(plan_path),
        "items": items,
        "neural_training_or_finetuning": False,
        "validation_ratings_read": False,
        "holdout_processed": False,
    }
    evidence = {
        "version": VERSION,
        "stage": "MACHINE_INPUTS_PREPARED_BEFORE_RATING_ACCESS",
        "plan_sha256": request["plan_sha256"],
        "validation_ids": list(VALIDATION_IDS),
        "items": evidence_items,
        "validation_ratings_read": False,
        "holdout_processed": False,
    }
    _write(local_root / "worker_request.json", request)
    _write(local_root / "machine_evidence.json", evidence)
    return request


def create_frozen_predictions(root: Path, local_root: Path) -> dict:
    """Apply only frozen P2.4D mappings; never read the three human ratings."""
    plan_path = root / PLAN_NAME
    plan = _load(plan_path)
    verify_frozen_plan(root, plan, include_ratings=False)
    request = _load(local_root / "worker_request.json")
    evidence = _load(local_root / "machine_evidence.json")
    raw = _load(local_root / "raw_multipa_outputs.json")
    raw_by_id = {pair_id: [] for pair_id in VALIDATION_IDS}
    for row in raw["items"]:
        if row["pair_id"] not in raw_by_id:
            raise ValueError("Unexpected ID in P2.5 MultiPA output")
        raw_by_id[row["pair_id"]].append(row)
    request_by_id = {item["pair_id"]: item for item in request["items"]}
    evidence_by_id = {item["pair_id"]: item for item in evidence["items"]}
    rows = []
    for pair_id in VALIDATION_IDS:
        aggregate = aggregate_video(raw_by_id[pair_id], len(request_by_id[pair_id]["chunks"]))
        if not aggregate["valid"]:
            raise ValueError(f"{pair_id}: MultiPA output invalid; no prediction fabricated")
        raw_score = aggregate["raw_pretrained_score"]
        fluency_features = evidence_by_id[pair_id]["fluency_features"]
        pronunciation = apply_fitted_mapping(
            plan["criteria"]["pronunciation"]["mapping"],
            "multipa_accuracy", raw_score["accuracy"])
        fluency = apply_mapping(plan["criteria"]["fluency"]["mapping"], fluency_features)
        prosody = apply_fitted_mapping(
            plan["criteria"]["prosody"]["mapping"],
            "multipa_prosody", raw_score["prosody"])
        coverage = evidence_by_id[pair_id]["completeness"]["coverage"]
        rows.append({
            "pair_id": pair_id,
            "pronunciation": pronunciation,
            "fluency": fluency,
            "prosody": prosody,
            "completeness": {
                "coverage": coverage,
                "criterion_score_1_5": round(1.0 + 4.0 * coverage, 4),
                "matched": len(evidence_by_id[pair_id]["completeness"]["matched_sequence"]),
                "omissions": len(evidence_by_id[pair_id]["completeness"]["omissions"]),
                "insertions": len(evidence_by_id[pair_id]["completeness"]["insertions"]),
                "warning": evidence_by_id[pair_id]["completeness"]["warning"],
            },
            "raw_multipa": raw_score,
            "raw_multipa_chunks": raw_by_id[pair_id],
            "fluency_features": fluency_features,
            "runtime_sec": aggregate["runtime_sec"],
        })
    result = {
        "version": VERSION,
        "stage": "FROZEN_PREDICTIONS_CREATED_BEFORE_RATING_ACCESS",
        "plan_sha256": sha256_file(plan_path),
        "validation_ids": list(VALIDATION_IDS),
        "predictions": rows,
        "validation_ratings_read": False,
        "training_or_refitting_performed": False,
        "machine_intelligibility_score": None,
        "overall_score": None,
        "holdout_processed": False,
    }
    _write(local_root / "frozen_predictions.json", result)
    return result


def _criterion_metrics(rows: list[dict], criterion: str) -> dict:
    human = np.asarray([row[f"teacher_{criterion}"] for row in rows], dtype=float)
    machine = np.asarray([row[f"machine_{criterion}"] for row in rows], dtype=float)
    error = np.abs(machine - human)
    rounded = np.clip(np.rint(machine), 1, 5)
    return {
        "n": len(rows),
        "mae": float(np.mean(error)),
        "exact_band_accuracy": float(np.mean(rounded == human)),
        "within_one_band_accuracy": float(np.mean(error <= 1.0)),
        "pearson_descriptive_only": correlation(machine.tolist(), human.tolist()),
        "spearman_descriptive_only": correlation(machine.tolist(), human.tolist(), rank=True),
        "prediction_standard_deviation": float(np.std(machine)),
        "prediction_collapse": bool(float(np.std(machine)) < 0.05),
    }


def _interpret(metric: dict, development_mae: float, policy: dict) -> tuple[str, str]:
    max_error = metric["max_absolute_error"]
    if (metric["mae"] <= development_mae + 0.15
            and not metric["prediction_collapse"] and max_error <= 1.0):
        signal = "GENERALIZATION_SIGNAL_POSITIVE"
    elif metric["mae"] <= development_mae + 0.35 and max_error <= 1.5:
        signal = "GENERALIZATION_SIGNAL_MIXED"
    else:
        signal = "GENERALIZATION_SIGNAL_WEAK"
    return signal, policy["recommendation_map"][signal]


def evaluate_frozen_predictions(root: Path, local_root: Path) -> dict:
    """Only this final stage opens teacher ratings; no fitting API is called."""
    plan_path = root / PLAN_NAME
    plan = _load(plan_path)
    verify_frozen_plan(root, plan, include_ratings=True)
    predictions = _load(local_root / "frozen_predictions.json")
    if predictions.get("validation_ratings_read") is not False:
        raise ValueError("Frozen prediction artifact has rating leakage")
    ratings = _load(root / RATINGS_PATH)
    if (ratings.get("completed_count") != 3 or ratings.get("pending_count") != 0
            or tuple(item["pair_id"] for item in ratings["items"]) != VALIDATION_IDS
            or not all(item.get("human_confirmed") for item in ratings["items"])):
        raise ValueError("P2.5 requires exactly three complete frozen validation ratings")
    prediction_by_id = {item["pair_id"]: item for item in predictions["predictions"]}
    rows = []
    for rating in ratings["items"]:
        pair_id = rating["pair_id"]
        prediction = prediction_by_id[pair_id]
        row = {"pair_id": pair_id,
               "teacher_intelligibility_reference_only": rating["intelligibility"],
               "machine_intelligibility": None,
               "completeness": prediction["completeness"],
               "raw_multipa": prediction["raw_multipa"],
               "overall": None}
        for criterion in ("pronunciation", "fluency", "prosody"):
            teacher = int(rating[criterion])
            machine = float(prediction[criterion])
            row[f"teacher_{criterion}"] = teacher
            row[f"machine_{criterion}"] = machine
            row[f"absolute_error_{criterion}"] = abs(machine - teacher)
        rows.append(row)
    metrics = {}
    interpretations = {}
    for criterion in ("pronunciation", "fluency", "prosody"):
        metric = _criterion_metrics(rows, criterion)
        metric["max_absolute_error"] = max(row[f"absolute_error_{criterion}"] for row in rows)
        signal, recommendation = _interpret(
            metric, plan["criteria"][criterion]["development_loo_mae"],
            plan["interpretation_policy"])
        metrics[criterion] = metric
        interpretations[criterion] = {
            "signal": signal,
            "competition_recommendation": recommendation,
            "development_loo_mae": plan["criteria"][criterion]["development_loo_mae"],
            "mini_validation_mae_delta": metric["mae"] - plan["criteria"][criterion]["development_loo_mae"],
        }
    result = {
        "version": VERSION,
        "status": "FROZEN_DEVELOPMENT_MINI_VALIDATION_COMPLETE",
        "plan_sha256": sha256_file(plan_path),
        "frozen_predictions_sha256": sha256_file(local_root / "frozen_predictions.json"),
        "validation_ratings_sha256": sha256_file(root / RATINGS_PATH),
        "rows": rows,
        "metrics": metrics,
        "interpretations": interpretations,
        "completeness_recommendation": "KEEP",
        "intelligibility": "HUMAN_ONLY / MACHINE_UNSTABLE",
        "overall": None,
        "correlation_warning": "N=3; Pearson and Spearman are descriptive only. No significance inference.",
        "validation_ratings_used_for_fitting": False,
        "scorer_changed_after_ratings": False,
        "holdout_processed": False,
    }
    _write(local_root / "p25_evaluation.json", result)
    return result
