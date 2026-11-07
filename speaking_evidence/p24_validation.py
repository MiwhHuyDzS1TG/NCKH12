"""Private three-video teacher workflow for frozen P2.4D mini-validation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from speaking_evidence.p22 import LABELS, RATING_IDS, _write_rating_atomically_with_snapshot, now_utc
from speaking_evidence.p24_validation_final import (
    EXCLUDED_IDS, FINAL_IDS, MANIFEST_NAME, MEMBERSHIP_SHA256,
    P24D_PLAN_SHA256, P24D_REPORT_SHA256, TARGET_COUNT,
    VERSION as FINAL_QUEUE_VERSION, load_final_queue_manifest,
    queue_membership_sha256, sha256_file,
)
from speaking_evidence.p24_validation_preflight import ORIGINAL_IDS


VERSION = "P2.4-development-validation-ratings-v2"
RATING_SCHEMA_VERSION = "P24-development-validation-three-item-four-criterion-v2"
VALIDATION_IDS = FINAL_IDS
PLAN_SHA256 = "28b2e4ef7c17214c202e09bcc1a5c01c7cecc309a81881c86dec21b81886836a"
WINNER_SHA256 = "caad327b1ef6881cc9273dc72bb8c34ab53faf67dd0ed8cde2e21ee5b024a7c6"
ORIGINAL_RATINGS_SHA256 = "6ffc1be2661c8ef3fbcf084c2cb4f83cec175d9f1996f20a444cdc6e13005f62"
HISTORICAL_RATING_SHA256 = "25f288e772fbe6d7e82accb30396ae4e5663aad9a22c2783f8ea63e471f0e32e"


def default_artifact_path(root: Path) -> Path:
    return root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v2.json"


def _assert_frozen_inputs(root: Path) -> dict:
    plan_path = root / "pretrained_model_tournament_v1.json"
    winner_path = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_path = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    historical_path = root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    if sha256_file(plan_path) != PLAN_SHA256:
        raise ValueError("Frozen P2.4 plan hash changed")
    if sha256_file(winner_path) != WINNER_SHA256:
        raise ValueError("Frozen P2.4 winner hash changed")
    if sha256_file(original_path) != ORIGINAL_RATINGS_SHA256:
        raise ValueError("Original 12-rating artifact changed")
    if sha256_file(historical_path) != HISTORICAL_RATING_SHA256:
        raise ValueError("Historical five-item validation artifact changed")
    winner = json.loads(winner_path.read_text(encoding="utf-8"))
    if (winner.get("status") != "MODEL_SELECTION_FROZEN_BEFORE_VALIDATION_RATINGS"
            or tuple(winner.get("development_validation_ids", [])) != ORIGINAL_IDS
            or winner.get("validation_human_ratings_read") is not False
            or winner.get("holdout_processed") is not False):
        raise ValueError("P2.4 winner freeze is not valid for development validation")
    manifest, manifest_sha = load_final_queue_manifest(root)
    if tuple(manifest["final_queue_ids"]) != VALIDATION_IDS:
        raise ValueError("Final validation manifest membership changed")
    return {"winner_sha256": sha256_file(winner_path),
            "final_manifest": manifest, "final_manifest_sha256": manifest_sha}


def validate_validation_rating_artifact(payload: dict) -> None:
    if payload.get("version") != VERSION or payload.get("rating_schema_version") != RATING_SCHEMA_VERSION:
        raise ValueError("Unexpected development-validation artifact version/schema")
    if payload.get("split") != "DEVELOPMENT_VALIDATION":
        raise ValueError("Validation ratings must remain in DEVELOPMENT_VALIDATION")
    ids = tuple(item.get("pair_id") for item in payload.get("items", []))
    if ids != VALIDATION_IDS or set(ids) & set(RATING_IDS) or set(ids) & set(EXCLUDED_IDS):
        raise ValueError("Development-validation queue membership changed")
    if tuple(payload.get("queue_ids", [])) != VALIDATION_IDS:
        raise ValueError("Development-validation queue declaration changed")
    if (payload.get("queue_membership_sha256") != MEMBERSHIP_SHA256
            or queue_membership_sha256(ids) != MEMBERSHIP_SHA256):
        raise ValueError("Development-validation queue hash changed")
    if payload.get("target_count") != TARGET_COUNT:
        raise ValueError("Development-validation target count changed")
    completed = sum(item.get("human_confirmed") is True for item in payload["items"])
    if (payload.get("completed_count") != completed
            or payload.get("pending_count") != TARGET_COUNT - completed):
        raise ValueError("Development-validation progress fields are inconsistent")
    if payload.get("p24_frozen_plan_sha256") != PLAN_SHA256:
        raise ValueError("Development-validation artifact has the wrong P2.4 plan hash")
    if (payload.get("p24d_scorer_plan_sha256") != P24D_PLAN_SHA256
            or payload.get("p24d_scorer_report_sha256") != P24D_REPORT_SHA256):
        raise ValueError("Development-validation artifact has the wrong P2.4D scorer hash")
    if payload.get("ratings_must_not_reselect_or_refit_scorer") is not True:
        raise ValueError("Validation ratings must not reselect/refit the scorer")
    if payload.get("automatic_p25") is not False or payload.get("automatic_calibration") is not False:
        raise ValueError("Validation completion must not start P2.5/calibration")
    frozen = payload.get("frozen_final_queue", {})
    if (frozen.get("version") != FINAL_QUEUE_VERSION
            or frozen.get("manifest_ref") != MANIFEST_NAME
            or tuple(frozen.get("final_queue_ids", [])) != VALIDATION_IDS
            or frozen.get("queue_membership_sha256") != MEMBERSHIP_SHA256):
        raise ValueError("Validation artifact is not bound to the frozen v3 queue")
    if tuple(payload.get("excluded_history", [])) != EXCLUDED_IDS:
        raise ValueError("Historical exclusions changed")
    expected_status = ("DEVELOPMENT_VALIDATION_RATINGS_COMPLETE"
                       if completed == TARGET_COUNT else "READY_FOR_TEACHER_RATING")
    if payload.get("status") != expected_status:
        raise ValueError("Development-validation artifact has the wrong status")
    for item in payload["items"]:
        if (item.get("split") != "DEVELOPMENT_VALIDATION"
                or item.get("audio_source_type") != "RAW_CROPPED"
                or item.get("canonical_source") != "RAW_COMPLETED_DUET"):
            raise ValueError("Validation item provenance changed")
        if item.get("rating_schema_version") != RATING_SCHEMA_VERSION:
            raise ValueError("Validation item schema changed")
        if item.get("requires_teacher_scorability_confirmation") is not False:
            raise ValueError("Final three items must be preflighted SCORABLE_CLEAN")
        for label in LABELS:
            value = item.get(label)
            if value is not None and (type(value) is not int or not 1 <= value <= 5):
                raise ValueError("Validation ratings must be null or integers from 1 to 5")
        if item.get("human_confirmed") is False and any(item.get(label) is not None for label in LABELS):
            raise ValueError("Unconfirmed validation item cannot contain ratings")


def initialize_validation_rating_artifact(root: Path, destination: Path | None = None) -> dict:
    """Create/read the v2 private rating artifact bound to the frozen v3 queue."""
    destination = destination or default_artifact_path(root)
    frozen = _assert_frozen_inputs(root)
    if destination.is_file():
        payload = json.loads(destination.read_text(encoding="utf-8"))
        validate_validation_rating_artifact(payload)
        if payload["frozen_final_queue"]["manifest_sha256"] != frozen["final_manifest_sha256"]:
            raise ValueError("Frozen final validation-manifest hash changed")
        return payload
    split = json.loads((root / "cohort_runs/T001_p14/data_split_v2.json").read_text(encoding="utf-8"))
    if not set(VALIDATION_IDS) <= set(split["development"]) or set(VALIDATION_IDS) & set(split["holdout"]):
        raise ValueError("P2.4D validation queue is not development-only")
    rows = json.loads((root / "cohort_runs/T001_p14/development_manifest_v3.json").read_text(encoding="utf-8"))
    row_by_id = {row["pair_id"]: row for row in rows}
    evidence_root = root / "assessment_runs/T001_p24_tournament_v1"
    inputs = json.loads((evidence_root / "validation_inputs_summary.json").read_text(encoding="utf-8"))
    input_by_id = {item["pair_id"]: item for item in inputs["items"]}
    if tuple(item["pair_id"] for item in inputs["items"]) != ORIGINAL_IDS:
        raise ValueError("Historical P2.4 machine-input queue changed")
    items = []
    for pair_id in VALIDATION_IDS:
        source, row = input_by_id[pair_id], row_by_id[pair_id]
        audio_path = evidence_root / source["model_input_ref"]
        if (source.get("canonical_source") != "RAW_COMPLETED_DUET"
                or source.get("scorability_status") != "SCORABLE_CLEAN"
                or not audio_path.is_file() or sha256_file(audio_path) != source["model_input_sha256"]):
            raise ValueError(f"Invalid frozen RAW_CROPPED teacher audio for {pair_id}")
        items.append({
            "pair_id": pair_id, "split": "DEVELOPMENT_VALIDATION",
            "quality_gate": row.get("quality_gate"),
            "source_scorability_status": source.get("scorability_status"),
            "requires_teacher_scorability_confirmation": False,
            "amber_scorability": None,
            "fluency": None, "pronunciation": None, "intelligibility": None, "prosody": None,
            "pronunciation_examples": "", "note": "", "human_confirmed": False,
            "rated_at_utc": None, "rating_schema_version": RATING_SCHEMA_VERSION,
            "audio_source_type": "RAW_CROPPED", "canonical_source": "RAW_COMPLETED_DUET",
            "raw_duet_path": row["duet_path"], "model_input_ref": source["model_input_ref"],
            "model_input_sha256": source["model_input_sha256"],
            "rater_metadata": {"rater_role": "TEACHER_RESEARCH_RATER",
                               "human_reviewed": False, "ai_assistance_used": True},
        })
    payload = {
        "version": VERSION, "rating_schema_version": RATING_SCHEMA_VERSION,
        "status": "READY_FOR_TEACHER_RATING", "created_at_utc": now_utc(),
        "split": "DEVELOPMENT_VALIDATION", "queue_ids": list(VALIDATION_IDS),
        "queue_membership_sha256": MEMBERSHIP_SHA256, "target_count": TARGET_COUNT,
        "completed_count": 0, "pending_count": TARGET_COUNT, "criteria": list(LABELS),
        "audio_source_type": "RAW_CROPPED", "rater_role": "TEACHER_RESEARCH_RATER",
        "human_reviewed": False, "ai_assistance_used": True,
        "p24_frozen_plan_sha256": PLAN_SHA256, "p24_winner_freeze_sha256": frozen["winner_sha256"],
        "p24d_scorer_plan_sha256": P24D_PLAN_SHA256,
        "p24d_scorer_report_sha256": P24D_REPORT_SHA256,
        "p24_model_selection_frozen": True, "ratings_must_not_reselect_or_refit_scorer": True,
        "automatic_p25": False, "automatic_calibration": False,
        "automatic_merge_into_original_12": False, "holdout_used": False,
        "original_12_ratings_sha256": ORIGINAL_RATINGS_SHA256,
        "excluded_history": list(EXCLUDED_IDS),
        "historical_private_artifact": {
            "ref": "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json",
            "sha256": HISTORICAL_RATING_SHA256, "preserved_unchanged": True,
        },
        "frozen_final_queue": {
            "version": FINAL_QUEUE_VERSION, "manifest_ref": MANIFEST_NAME,
            "manifest_sha256": frozen["final_manifest_sha256"],
            "queue_membership_sha256": MEMBERSHIP_SHA256,
            "final_queue_ids": list(VALIDATION_IDS),
        },
        "technical_exclusions": frozen["final_manifest"]["technical_exclusions"],
        "items": items, "history": [],
    }
    validate_validation_rating_artifact(payload)
    _write_rating_atomically_with_snapshot(destination, payload)
    return payload


def save_validation_rating(path: Path, root: Path, pair_id: str, scorability: str,
                           scores: dict, pronunciation_examples: str = "") -> dict:
    """Persist one rating while rechecking every membership/hash guard."""
    frozen = _assert_frozen_inputs(root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_validation_rating_artifact(payload)
    if payload["frozen_final_queue"]["manifest_sha256"] != frozen["final_manifest_sha256"]:
        raise ValueError("Frozen final validation-manifest hash changed")
    if pair_id not in VALIDATION_IDS:
        raise ValueError("Only frozen v3 development-validation IDs may be rated")
    if scorability != "SCORABLE":
        raise ValueError("Final v3 queue contains only preflighted SCORABLE_CLEAN items")
    if any(type(scores.get(name)) is not int or not 1 <= scores[name] <= 5 for name in LABELS):
        raise ValueError("All four validation ratings must be integers from 1 to 5")
    item = next(row for row in payload["items"] if row["pair_id"] == pair_id)
    if item.get("human_confirmed") is True:
        payload["history"].append({"pair_id": pair_id, "superseded_at_utc": now_utc(),
                                   "previous_rating": copy.deepcopy(item)})
    item.update({**scores, "amber_scorability": "NOT_REQUIRED",
                 "pronunciation_examples": pronunciation_examples,
                 "human_confirmed": True, "rated_at_utc": now_utc(),
                 "rater_metadata": {**item["rater_metadata"], "human_reviewed": True}})
    completed = sum(row.get("human_confirmed") is True for row in payload["items"])
    payload.update({"completed_count": completed, "pending_count": TARGET_COUNT - completed,
                    "human_reviewed": completed > 0,
                    "status": ("DEVELOPMENT_VALIDATION_RATINGS_COMPLETE"
                               if completed == TARGET_COUNT else "READY_FOR_TEACHER_RATING")})
    validate_validation_rating_artifact(payload)
    _write_rating_atomically_with_snapshot(path, payload)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    validate_validation_rating_artifact(persisted)
    return next(row for row in persisted["items"] if row["pair_id"] == pair_id)


def rating_progress(payload: dict) -> tuple[int, int]:
    validate_validation_rating_artifact(payload)
    return payload["completed_count"], TARGET_COUNT
