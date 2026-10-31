"""Support-aware P2.2C calibration and immutable human-rating provenance.

This module never invents labels, never alters the source rating artifact and
never reads holdout media.  Two-level models are explicitly restricted to the
human-observed support; one-level criteria remain evidence-only.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


SUPPORT_AWARE_VERSION = "P2.2C-support-aware-v1"
PROVENANCE_CLASS = "HUMAN_REVIEWED_AI_ASSISTED"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def freeze_rating_snapshot(ratings_path: Path, destination_dir: Path,
                           audio_audit: dict) -> dict:
    """Create an exact immutable snapshot plus provenance without editing labels."""
    source_bytes = ratings_path.read_bytes()
    payload = json.loads(source_bytes)
    items = payload.get("items", [])
    confirmed = [item for item in items if item.get("human_confirmed") is True]
    if len(confirmed) != len(items) or not items:
        raise ValueError("The frozen P2.2C snapshot requires a complete human-confirmed queue")
    raw_hash = _sha256_bytes(source_bytes)
    snapshot_path = destination_dir / "ratings_v2_frozen_p22c_v1.json"
    manifest_path = destination_dir / "ratings_v2_frozen_p22c_manifest_v1.json"
    if snapshot_path.is_file() and snapshot_path.read_bytes() != source_bytes:
        raise ValueError("Frozen P2.2C snapshot already exists with different source bytes")
    if not snapshot_path.is_file():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(source_bytes)
    snapshot_hash = _sha256_bytes(snapshot_path.read_bytes())
    if snapshot_hash != raw_hash:
        raise ValueError("Frozen rating snapshot hash does not match the source artifact")
    criteria = ("fluency", "pronunciation", "intelligibility", "prosody")
    distributions = {
        criterion: {str(level): count for level, count in sorted(Counter(
            item[criterion] for item in confirmed
        ).items())}
        for criterion in criteria
    }
    manifest = {
        "version": SUPPORT_AWARE_VERSION,
        "status": "FROZEN_IMMUTABLE_SOURCE_DATA",
        "created_at_utc": _now_utc(),
        "source_ref": str(ratings_path).replace("\\", "/"),
        "snapshot_ref": str(snapshot_path).replace("\\", "/"),
        "source_sha256": raw_hash,
        "snapshot_sha256": snapshot_hash,
        "byte_exact_snapshot": True,
        "raw_labels_modified": False,
        "confirmed_count": len(confirmed),
        "observed_distributions": distributions,
        "rating_provenance": {
            "classification": PROVENANCE_CLASS,
            "rater_role": "TEACHER_RESEARCH_RATER",
            "human_reviewed": True,
            "ai_assistance_used": True,
            "ai_assistance_context": (
                "The teacher personally reviewed the learner audio and made/accepted the final "
                "ratings with assistance from a ChatGPT conversation in the NCKH12 project."
            ),
            "final_decision_human_confirmed": True,
            "independent_human_gold_standard": False,
            "inter_rater_reliability_available": False,
            "rating_schema_version": payload.get("schema_version"),
            "source_timestamps_preserved_in_snapshot": True,
            "audio_source_type": audio_audit.get("teacher_rating_audio_source"),
        },
        "audio_source_audit": audio_audit,
        "allowed_uses": [
            "PRELIMINARY_DEVELOPMENT_CALIBRATION",
            "ENGINEERING_SELECTION",
            "COMPETITION_PROTOTYPE_CALIBRATION",
        ],
        "prohibited_claim": "INDEPENDENT_FINAL_HUMAN_VALIDATION",
        "holdout_used": False,
    }
    _write_json(manifest_path, manifest)
    return manifest


def audit_teacher_rating_audio(evidence_root: Path, ratings: list[dict]) -> dict:
    """Classify the actual media exposed by the teacher page from artifact provenance."""
    checks = []
    for item in ratings:
        pair_id = item["pair_id"]
        pair_root = evidence_root / "pairs" / pair_id
        raw = json.loads((pair_root / "raw_evidence.json").read_text(encoding="utf-8"))
        evidence = json.loads((pair_root / "evidence.json").read_text(encoding="utf-8"))
        model_ref = raw.get("model_input_ref")
        canonical = evidence.get("audio_provenance", {}).get("canonical_source")
        model_path = evidence_root / str(model_ref)
        forbidden_name = any(token in model_path.name.lower() for token in ("residual", "cancel"))
        checks.append({
            "pair_id": pair_id,
            "raw_video_presented": bool(raw.get("raw_duet_path")),
            "model_input_presented": model_path.is_file(),
            "canonical_source": canonical,
            "model_input_ref": str(model_ref).replace("\\", "/"),
            "residual_or_cancellation_filename": forbidden_name,
            "extractor_contract": "FFMPEG_RAW_DUET_CROP_WITH_NONCANDIDATE_SAMPLES_ZEROED",
        })
    raw_cropped = bool(checks) and all(
        row["raw_video_presented"] and row["model_input_presented"]
        and row["canonical_source"] == "RAW_COMPLETED_DUET"
        and not row["residual_or_cancellation_filename"]
        for row in checks
    )
    return {
        "version": SUPPORT_AWARE_VERSION,
        "teacher_rating_audio_source": "RAW_CROPPED" if raw_cropped else "UNKNOWN",
        "ui_media": ["RAW_COMPLETED_DUET_VIDEO", "RAW_DUET_DERIVED_CROPPED_MASKED_WAV"],
        "generation_path": (
            "prepare_turn_audio: ffmpeg extracts mono 16 kHz PCM16 directly from the raw completed "
            "Duet, crops to the task turn, then zeros samples outside Phase-1 learner intervals"
        ),
        "cancellation_or_residual_used": False if raw_cropped else None,
        "artifact_count_checked": len(checks),
        "items": checks,
        "limitation": (
            "The WAV is raw-source-derived but time-masked; it is not source-separated and may "
            "still contain background/template sound inside learner intervals."
        ),
    }


def _standardize(train_x: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0)
    scale[scale < 1e-9] = 1.0
    return (train_x - mean) / scale, (test_x - mean) / scale, mean, scale


def _logistic_fit(x: np.ndarray, y: np.ndarray, alpha: float,
                  iterations: int = 100) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    beta = np.zeros(design.shape[1], dtype=float)
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    for _ in range(iterations):
        linear = np.clip(design @ beta, -30.0, 30.0)
        probability = 1.0 / (1.0 + np.exp(-linear))
        weights = np.maximum(probability * (1.0 - probability), 1e-6)
        gradient = design.T @ (probability - y) + penalty @ beta
        hessian = design.T @ (weights[:, None] * design) + penalty
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    return beta


def _probability(beta: np.ndarray, x: np.ndarray) -> float:
    value = float(np.r_[1.0, x] @ beta)
    return float(1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, value)))))


def fit_restricted_binary_mapping(rows: list[dict], label: str,
                                  feature_names: tuple[str, ...], alpha: float = 2.0) -> dict:
    """LOOCV logistic mapping whose expected score cannot leave observed support."""
    y_raw = np.asarray([int(row[label]) for row in rows], dtype=int)
    support = sorted(set(y_raw.tolist()))
    if len(rows) < 8:
        return {"status": "INSUFFICIENT_HUMAN_LABELS", "available": len(rows), "required": 8}
    if len(support) != 2:
        raise ValueError("Restricted binary calibration requires exactly two observed levels")
    low, high = support
    y = (y_raw == high).astype(float)
    x = np.asarray([[float(row[name]) for name in feature_names] for row in rows], dtype=float)
    probabilities = []
    expected = []
    for index in range(len(rows)):
        keep = np.arange(len(rows)) != index
        train_x, test_x, _, _ = _standardize(x[keep], x[index:index + 1])
        beta = _logistic_fit(train_x, y[keep], alpha)
        probability = _probability(beta, test_x[0])
        probabilities.append(probability)
        expected.append(low + (high - low) * probability)
    standardized, _, feature_mean, feature_scale = _standardize(x, x[:1])
    beta = _logistic_fit(standardized, y, alpha)
    predicted_class = np.asarray([high if p >= 0.5 else low for p in probabilities])
    accuracy = float(np.mean(predicted_class == y_raw))
    recalls = [float(np.mean(predicted_class[y_raw == level] == level)) for level in support]
    balanced_accuracy = float(np.mean(recalls))
    collapsed = len(set(predicted_class.tolist())) < 2
    counts = Counter(y_raw.tolist())
    severe_imbalance = min(counts.values()) < 3
    stable = not severe_imbalance and not collapsed and balanced_accuracy >= 0.5
    absolute_errors = np.abs(np.asarray(expected) - y_raw)
    status = ("DEVELOPMENT_PRELIMINARY_RANGE_LIMITED" if stable
              else "MACHINE_CALIBRATION_UNSTABLE")
    return {
        "status": status,
        "exploratory_model_fitted": True,
        "model": "ridge_regularized_binary_logistic_expected_score",
        "alpha": alpha,
        "features": list(feature_names),
        "observed_support": support,
        "output_constraint": [low, high],
        "support_label": f"CALIBRATED_WITHIN_OBSERVED_RANGE_{low}_TO_{high}",
        "n": len(rows),
        "label_distribution": {str(level): counts[level] for level in support},
        "feature_mean": feature_mean.tolist(),
        "feature_scale": feature_scale.tolist(),
        "intercept": float(beta[0]),
        "coefficients": beta[1:].tolist(),
        "validation": "LEAVE_ONE_OUT",
        "loo_mae": float(np.mean(absolute_errors)),
        "classification_accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        "majority_class_collapse": collapsed,
        "severe_imbalance": severe_imbalance,
        "within_observed_level_agreement": accuracy,
        "predicted_vs_human": [
            {"pair_id": row.get("pair_id", f"row_{index + 1:03d}"),
             "human": int(y_raw[index]),
             "probability_high_level": round(probabilities[index], 6),
             "predicted_expected_score": round(expected[index], 4),
             "predicted_class": int(predicted_class[index]),
             "absolute_error": round(float(absolute_errors[index]), 4)}
            for index, row in enumerate(rows)
        ],
        "learner_facing_score_allowed": stable,
        "uncertainty": (
            "N=12 restricted-range development sample; outputs cannot extrapolate beyond observed support."
        ),
    }


def apply_restricted_binary_mapping(mapping: dict, features: dict) -> float | None:
    if mapping.get("status") != "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED":
        return None
    x = np.asarray([float(features[name]) for name in mapping["features"]])
    z = (x - np.asarray(mapping["feature_mean"])) / np.asarray(mapping["feature_scale"])
    probability = _probability(np.r_[mapping["intercept"], mapping["coefficients"]], z)
    low, high = mapping["observed_support"]
    return round(float(low + (high - low) * probability), 2)


def select_coverage_expansion(development_rows: list[dict], split: dict,
                              existing_ids: tuple[str, ...], count: int = 6) -> dict:
    """Select only machine-evidence-diverse development candidates, never labels."""
    development, holdout = set(split["development"]), set(split["holdout"])
    existing = set(existing_ids)
    eligible = [row for row in development_rows
                if row.get("pair_id") in development
                and row.get("pair_id") not in existing
                and row.get("pair_id") not in holdout
                and row.get("quality_gate") != "RED"
                and row.get("scorability_status") in {
                    "SCORABLE_CLEAN", "SCORABLE_AFTER_CANCELLATION"
                }]
    feature_names = (
        "learner_duration_sec", "scorability_confidence", "reference_audio_presence_score",
        "speech_to_background_db", "speech_level_dbfs_median",
    )

    def vector(row: dict) -> list[float]:
        quality = row.get("audio_quality_features") or {}
        values = {
            "learner_duration_sec": row.get("learner_duration_sec"),
            "scorability_confidence": row.get("scorability_confidence"),
            "reference_audio_presence_score": row.get("reference_audio_presence_score"),
            "speech_to_background_db": quality.get("speech_to_background_db"),
            "speech_level_dbfs_median": quality.get("speech_level_dbfs_median"),
        }
        return [float(values[name]) if values[name] is not None else 0.0 for name in feature_names]

    pool = eligible + [row for row in development_rows if row.get("pair_id") in existing]
    matrix = np.asarray([vector(row) for row in pool], dtype=float)
    mean = matrix.mean(axis=0) if len(matrix) else np.zeros(len(feature_names))
    scale = matrix.std(axis=0) if len(matrix) else np.ones(len(feature_names))
    scale[scale < 1e-9] = 1.0
    normalized = {row["pair_id"]: (np.asarray(vector(row)) - mean) / scale for row in pool}
    anchors = [normalized[pair_id] for pair_id in existing if pair_id in normalized]
    remaining = sorted(eligible, key=lambda row: row["pair_id"])
    selected = []
    while remaining and len(selected) < count:
        def distance(row: dict) -> tuple[float, str]:
            point = normalized[row["pair_id"]]
            references = anchors + [normalized[item["pair_id"]] for item in selected]
            minimum = min((float(np.linalg.norm(point - ref)) for ref in references), default=0.0)
            return minimum, row["pair_id"]
        chosen = max(remaining, key=distance)
        minimum_distance = distance(chosen)[0]
        selected.append({
            "pair_id": chosen["pair_id"],
            "quality_gate": chosen.get("quality_gate"),
            "scorability_status": chosen.get("scorability_status"),
            "selection_reason": "DETERMINISTIC_GREEDY_MACHINE_FEATURE_COVERAGE",
            "distance_from_existing_or_selected": round(minimum_distance, 6),
            "machine_feature_values": dict(zip(feature_names, vector(chosen))),
            "human_score_used_for_selection": False,
            "requires_teacher_scorability_confirmation": (
                chosen.get("scorability_status") != "SCORABLE_CLEAN"
            ),
        })
        remaining = [row for row in remaining if row["pair_id"] != chosen["pair_id"]]
    return {
        "version": SUPPORT_AWARE_VERSION,
        "status": "OPTIONAL_DEVELOPMENT_COVERAGE_EXPANSION",
        "created_at_utc": _now_utc(),
        "requested_approximate_count": count,
        "selected_count": len(selected),
        "selected_ids": [item["pair_id"] for item in selected],
        "items": selected,
        "feature_specification": list(feature_names),
        "selection_uses_human_scores": False,
        "selection_goal": "MAXIMIZE_PRE_EXISTING_MACHINE_FEATURE_COVERAGE_NOT_FIND_LOW_SCORES",
        "eligibility": ["DEVELOPMENT_ONLY", "NOT_RED", "SCORABLE_CLEAN_OR_AFTER_CANCELLATION"],
        "split_proof": {
            "all_selected_in_development": all(item["pair_id"] in development for item in selected),
            "selected_holdout_intersection": sorted({item["pair_id"] for item in selected} & holdout),
            "holdout_media_opened": False,
        },
        "limitation": (
            "Only five additional candidates satisfy the frozen scorability policy; no unsafe sixth "
            "candidate is added merely to meet a nominal count."
            if len(selected) < count else None
        ),
    }
