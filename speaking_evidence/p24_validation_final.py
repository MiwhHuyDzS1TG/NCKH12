"""Frozen three-item queue created after pre-rating technical exclusions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


VERSION = "P2.4-development-validation-final-queue-v3"
MANIFEST_NAME = "p24_validation_final_queue_v3.json"
ORIGINAL_IDS = (
    "T001-D006", "T001-D023", "T001-D064", "T001-D043", "T001-D048",
)
EXCLUDED_IDS = ("T001-D006", "T001-D023")
FINAL_IDS = ("T001-D064", "T001-D043", "T001-D048")
TARGET_COUNT = 3
EXCLUSION_REASON = "PRE_RATING_TECHNICAL_ELIGIBILITY_EXCLUSION"
MEMBERSHIP_SHA256 = "116db3582ea73fba69aff7cf57562c2f47e28764df114fd9196b56439e1a4af6"
P24D_PLAN_SHA256 = "90755aaa169b605c7b9a070ae411dc28366a2b3e568e4daf2e81dc15a4cee1c1"
P24D_REPORT_SHA256 = "b7824a624a8197db59f297e9f328bb0fdcb2d3400c4e4ae323bf6838786deecb"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def queue_membership_sha256(ids: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def validate_final_queue_manifest(payload: dict) -> None:
    if payload.get("version") != VERSION:
        raise ValueError("Unexpected final validation-queue version")
    if payload.get("status") != "FINAL_THREE_ITEM_QUEUE_FROZEN_FOR_TEACHER_RATING":
        raise ValueError("Final validation queue is not frozen for teacher rating")
    history = payload.get("historical_queue", {})
    if tuple(history.get("original_ids", [])) != ORIGINAL_IDS:
        raise ValueError("Original five-item validation history changed")
    if history.get("ratings_completed_before_migration") != 0:
        raise ValueError("Final queue migration must precede all teacher ratings")
    if tuple(payload.get("excluded_ids", [])) != EXCLUDED_IDS:
        raise ValueError("Technical exclusions changed")
    exclusions = payload.get("technical_exclusions", [])
    if tuple(item.get("pair_id") for item in exclusions) != EXCLUDED_IDS:
        raise ValueError("Technical exclusion order or membership changed")
    for item in exclusions:
        if item.get("decision") != "NOT_SCORABLE / EXCLUDE_FROM_VALIDATION":
            raise ValueError("Excluded validation item has the wrong decision")
        if item.get("reason") != EXCLUSION_REASON or item.get("replacement") is not None:
            raise ValueError("Excluded validation item has the wrong reason/replacement")
    ids = tuple(payload.get("final_queue_ids", []))
    if ids != FINAL_IDS or len(set(ids)) != TARGET_COUNT:
        raise ValueError("Final three-item validation membership changed")
    if payload.get("target_count") != TARGET_COUNT or payload.get("final_queue_count") != TARGET_COUNT:
        raise ValueError("Final validation target count changed")
    if payload.get("queue_membership_sha256") != MEMBERSHIP_SHA256:
        raise ValueError("Frozen queue-membership hash changed")
    if queue_membership_sha256(ids) != MEMBERSHIP_SHA256:
        raise ValueError("Final queue does not match its membership hash")
    if payload.get("eligible_development_pool_exhausted") is not True:
        raise ValueError("Exhausted development replacement pool is not recorded")
    if payload.get("replacement_status") != "NO_REPLACEMENTS_AVAILABLE_ELIGIBLE_DEVELOPMENT_POOL_EXHAUSTED":
        raise ValueError("Replacement status changed")
    if payload.get("replacement_threshold_lowered") is not False:
        raise ValueError("Replacement threshold must not be lowered")
    if payload.get("selection_uses_teacher_ratings") is not False:
        raise ValueError("Teacher ratings must not select queue membership")
    if payload.get("validation_progress") != "0/3":
        raise ValueError("Final queue must start at 0/3")
    if payload.get("all_ratings_null_before_teacher") is not True:
        raise ValueError("Final queue must start with null ratings")
    if payload.get("ratings_must_not_reselect_or_refit_scorer") is not True:
        raise ValueError("Validation ratings must not change the frozen scorer")
    if payload.get("automatic_p25") is not False or payload.get("automatic_calibration") is not False:
        raise ValueError("Queue completion must not start P2.5/calibration")
    proof = payload.get("split_proof", {})
    if proof.get("all_final_ids_in_development") is not True:
        raise ValueError("Final queue is not development-only")
    if proof.get("final_holdout_intersection") or proof.get("holdout_media_opened") is not False:
        raise ValueError("Holdout invariant failed")


def load_final_queue_manifest(root: Path) -> tuple[dict, str]:
    path = root / MANIFEST_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_final_queue_manifest(payload)
    history = payload["historical_queue"]
    for ref_key, hash_key in (
        ("v1_manifest_ref", "v1_manifest_sha256"),
        ("v2_manifest_ref", "v2_manifest_sha256"),
        ("private_v1_rating_artifact_ref", "private_v1_rating_artifact_sha256"),
    ):
        if sha256_file(root / history[ref_key]) != history[hash_key]:
            raise ValueError(f"Historical validation artifact changed: {history[ref_key]}")
    if sha256_file(root / "p24d_multipa_plan_v1.json") != P24D_PLAN_SHA256:
        raise ValueError("Frozen P2.4D scorer plan changed")
    if sha256_file(root / "MULTIPA_COMPETITION_SCORER_REPORT.md") != P24D_REPORT_SHA256:
        raise ValueError("Frozen P2.4D scorer report changed")
    return payload, sha256_file(path)
