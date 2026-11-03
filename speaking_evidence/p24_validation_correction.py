"""Manual technical exclusions applied after the frozen P2.4 preflight."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from speaking_evidence.p22 import LABELS, _write_rating_atomically_with_snapshot
from speaking_evidence.p24_validation_preflight import (
    ORIGINAL_IDS,
    PLAN_SHA256,
    SCORABLE_STATUSES,
)


VERSION = "P2.4-validation-scorability-correction-v2"
MANIFEST_NAME = "p24_validation_replacement_manifest_v2.json"
FORCED_EXCLUSIONS = ("T001-D006", "T001-D023")
FINAL_IDS = ("T001-D064", "T001-D043", "T001-D048")
TARGET_COUNT = 5


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_corrected_manifest(root: Path, destination: Path | None = None) -> dict:
    """Freeze the manual exclusions without weakening the replacement policy."""
    destination = destination or root / MANIFEST_NAME
    if destination.is_file():
        payload = _load(destination)
        validate_corrected_manifest(payload)
        return payload

    ratings_path = root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    ratings = _load(ratings_path)
    if any(item.get(label) is not None for item in ratings["items"] for label in LABELS):
        raise ValueError("Criterion rating exists; manual queue correction is no longer safe")
    if any(item.get("human_confirmed") is True and item.get("pair_id") not in FORCED_EXCLUSIONS
           for item in ratings["items"]):
        raise ValueError("A retained validation item has already been rated")

    v1 = _load(root / "p24_validation_replacement_manifest_v1.json")
    rows = _load(root / "cohort_runs/T001_p14/development_manifest_v3.json")
    row_by_id = {row["pair_id"]: row for row in rows}
    split = _load(root / "cohort_runs/T001_p14/data_split_v2.json")
    development, holdout = set(split["development"]), set(split["holdout"])

    exclusions = []
    for pair_id in FORCED_EXCLUSIONS:
        row = row_by_id[pair_id]
        exclusions.append({
            "pair_id": pair_id,
            "decision": "NOT_SCORABLE / EXCLUDE_FROM_VALIDATION",
            "replacement_decision": "REPLACE_TECHNICAL_FAILURE",
            "decision_source": "MANUAL_TECHNICAL_REVIEW_CONFIRMED_BY_RESEARCHER",
            "p1_status": row.get("quality_gate"),
            "p1_scorability": row.get("scorability_status"),
            "quality_gate_reason_codes": row.get("quality_gate_reasons", []),
            "p1_scorability_reasons": row.get("scorability_reasons", []),
            "p1_audio_presence_reasons": row.get("reasons", []),
            "p1_warnings": row.get("warnings", []),
            "reference_contamination_scope": row.get("reference_contamination_scope"),
            "audio_state": row.get("audio_state"),
            "low_speech_level": row.get("low_speech_level"),
            "background_interference": row.get("background_interference"),
        })

    # The v1 ranking was frozen before validation. It is empty because every
    # remaining non-calibration development item is REVIEW_REQUIRED or RED and
    # lacks a frozen RAW_CROPPED validation input. The threshold is not relaxed.
    frozen_ranking = v1["deterministic_backup_ranking"]
    replacements = []
    if frozen_ranking:
        raise ValueError("Unexpected v1 backup candidates require individual preflight")

    payload = {
        "version": VERSION,
        "created_at_utc": _now_utc(),
        "status": "ELIGIBLE_DEVELOPMENT_POOL_EXHAUSTED",
        "target_count": TARGET_COUNT,
        "original_five_ids": list(ORIGINAL_IDS),
        "technical_exclusions": exclusions,
        "excluded_ids": list(FORCED_EXCLUSIONS),
        "frozen_backup_ranking_source": "p24_validation_replacement_manifest_v1.json",
        "frozen_backup_ranking_sha256": _sha256(
            root / "p24_validation_replacement_manifest_v1.json"
        ),
        "deterministic_backup_ranking": frozen_ranking,
        "eligible_replacement_pool": [],
        "replacements": replacements,
        "replacement_pool_exhausted": True,
        "replacement_threshold_lowered": False,
        "selection_uses_teacher_ratings": False,
        "retained_scorable_ids": list(FINAL_IDS),
        "final_queue_ids": list(FINAL_IDS),
        "final_queue_count": len(FINAL_IDS),
        "five_item_queue_complete": False,
        "all_retained_items_scorable": all(
            row_by_id[pair_id].get("scorability_status") in SCORABLE_STATUSES
            for pair_id in FINAL_IDS
        ),
        "all_final_items_scorable": False,
        "validation_progress": "0/5",
        "p24_frozen_plan_sha256": PLAN_SHA256,
        "p24_model_selection_unchanged": True,
        "original_12_ratings_sha256": ratings["original_12_ratings_sha256"],
        "split_proof": {
            "all_retained_in_development": set(FINAL_IDS) <= development,
            "retained_holdout_intersection": sorted(set(FINAL_IDS) & holdout),
            "holdout_count_membership_only": len(holdout),
            "holdout_media_opened": False,
        },
    }
    validate_corrected_manifest(payload)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def validate_corrected_manifest(payload: dict) -> None:
    if payload.get("version") != VERSION:
        raise ValueError("Unexpected corrected validation-manifest version")
    if tuple(payload.get("original_five_ids", [])) != ORIGINAL_IDS:
        raise ValueError("Original validation selection changed")
    if tuple(payload.get("excluded_ids", [])) != FORCED_EXCLUSIONS:
        raise ValueError("Manual technical exclusions changed")
    if tuple(payload.get("final_queue_ids", [])) != FINAL_IDS:
        raise ValueError("Corrected validation queue changed")
    if payload.get("replacement_pool_exhausted") is not True:
        raise ValueError("Correction does not record exhausted replacement pool")
    if payload.get("replacement_threshold_lowered") is not False:
        raise ValueError("Scorability threshold must not be lowered")
    if payload.get("selection_uses_teacher_ratings") is not False:
        raise ValueError("Teacher ratings must not select replacements")
    if payload.get("deterministic_backup_ranking") != [] or payload.get("replacements") != []:
        raise ValueError("No eligible frozen replacement exists")
    if payload.get("validation_progress") != "0/5":
        raise ValueError("Corrected validation must remain at 0/5")
    if payload.get("five_item_queue_complete") is not False:
        raise ValueError("Correction must not claim a complete five-item queue")
    if payload.get("all_retained_items_scorable") is not True:
        raise ValueError("A retained validation candidate is not scorable")
    if payload.get("all_final_items_scorable") is not False:
        raise ValueError("A five-item scorable validation queue does not exist")
    if payload.get("p24_frozen_plan_sha256") != PLAN_SHA256:
        raise ValueError("Frozen P2.4 plan hash changed")
    proof = payload.get("split_proof", {})
    if proof.get("all_retained_in_development") is not True or proof.get(
        "retained_holdout_intersection"
    ):
        raise ValueError("Corrected queue is not development-only")


def rebuild_empty_blocked_queue(root: Path, manifest_path: Path | None = None) -> dict:
    """Remove excluded IDs at zero criterion ratings and block teacher scoring."""
    manifest_path = manifest_path or root / MANIFEST_NAME
    manifest = _load(manifest_path)
    validate_corrected_manifest(manifest)
    ratings_path = root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    payload = _load(ratings_path)
    if any(item.get(label) is not None for item in payload["items"] for label in LABELS):
        raise ValueError("Cannot rebuild after a criterion rating exists")
    retained = {item["pair_id"]: item for item in payload["items"] if item["pair_id"] in FINAL_IDS}
    if set(retained) != set(FINAL_IDS):
        raise ValueError("A retained validation item is missing")
    for item in retained.values():
        if item.get("human_confirmed") is True:
            raise ValueError("A retained validation item was already rated")
        item["amber_scorability"] = None
        item["rated_at_utc"] = None
        for label in LABELS:
            item[label] = None
    payload.update({
        "status": "BLOCKED_INSUFFICIENT_SCORABLE_DEVELOPMENT_POOL",
        "queue_ids": list(FINAL_IDS),
        "target_count": TARGET_COUNT,
        "eligible_count": len(FINAL_IDS),
        "human_reviewed": False,
        "technical_exclusions": manifest["technical_exclusions"],
        "pre_rating_scorability_preflight": {
            "version": VERSION,
            "manifest_ref": MANIFEST_NAME,
            "manifest_sha256": _sha256(manifest_path),
            "completed_before_criterion_rating": True,
            "replacement_pool_exhausted": True,
            "final_queue_ids": list(FINAL_IDS),
        },
        "items": [retained[pair_id] for pair_id in FINAL_IDS],
    })
    _write_rating_atomically_with_snapshot(ratings_path, payload)
    return payload
