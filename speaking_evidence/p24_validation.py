"""Private five-video teacher workflow for frozen P2.4 development validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from speaking_evidence.p24_validation_correction import (
    FINAL_IDS,
    MANIFEST_NAME,
    TARGET_COUNT,
    VERSION as PREFLIGHT_VERSION,
    validate_corrected_manifest,
)
from speaking_evidence.p24_validation_preflight import (
    ORIGINAL_IDS,
)

from speaking_evidence.p22 import (
    LABELS,
    RATING_IDS,
    _write_rating_atomically_with_snapshot,
    now_utc,
)


VERSION = "P2.4-development-validation-ratings-v1"
RATING_SCHEMA_VERSION = "P24-development-validation-four-criterion-v1"
VALIDATION_IDS = FINAL_IDS
PLAN_SHA256 = "28b2e4ef7c17214c202e09bcc1a5c01c7cecc309a81881c86dec21b81886836a"
ORIGINAL_RATINGS_SHA256 = "6ffc1be2661c8ef3fbcf084c2cb4f83cec175d9f1996f20a444cdc6e13005f62"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_artifact_path(root: Path) -> Path:
    return root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"


def _assert_frozen_inputs(root: Path) -> dict:
    plan_path = root / "pretrained_model_tournament_v1.json"
    winner_path = root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"
    original_path = root / "human_ground_truth/p22a_v1/ratings_v2.json"
    if _sha256(plan_path) != PLAN_SHA256:
        raise ValueError("Frozen P2.4 plan hash changed")
    if _sha256(original_path) != ORIGINAL_RATINGS_SHA256:
        raise ValueError("Original 12-rating artifact changed")
    winner = json.loads(winner_path.read_text(encoding="utf-8"))
    if (winner.get("status") != "MODEL_SELECTION_FROZEN_BEFORE_VALIDATION_RATINGS"
            or tuple(winner.get("development_validation_ids", [])) != ORIGINAL_IDS
            or winner.get("validation_human_ratings_read") is not False
            or winner.get("holdout_processed") is not False):
        raise ValueError("P2.4 winner freeze is not valid for development validation")
    preflight_path = root / MANIFEST_NAME
    if not preflight_path.is_file():
        raise ValueError("Pre-rating validation scorability preflight is missing")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    validate_corrected_manifest(preflight)
    if tuple(preflight["final_queue_ids"]) != VALIDATION_IDS:
        raise ValueError("Validation queue does not match the frozen scorability preflight")
    return {
        "winner_sha256": _sha256(winner_path),
        "winner": winner,
        "preflight_sha256": _sha256(preflight_path),
        "preflight": preflight,
    }


def validate_validation_rating_artifact(payload: dict) -> None:
    if payload.get("version") != VERSION:
        raise ValueError("Unexpected development-validation artifact version")
    if payload.get("rating_schema_version") != RATING_SCHEMA_VERSION:
        raise ValueError("Unexpected development-validation rating schema")
    if payload.get("split") != "DEVELOPMENT_VALIDATION":
        raise ValueError("Validation ratings must remain in DEVELOPMENT_VALIDATION")
    ids = tuple(item.get("pair_id") for item in payload.get("items", []))
    if ids != VALIDATION_IDS or set(ids) & set(RATING_IDS):
        raise ValueError("Development-validation queue membership changed")
    if payload.get("p24_frozen_plan_sha256") != PLAN_SHA256:
        raise ValueError("Development-validation artifact has the wrong frozen-plan hash")
    if payload.get("ratings_must_not_reselect_p24_models") is not True:
        raise ValueError("Validation ratings must not reselect P2.4 models")
    if payload.get("automatic_calibration_after_completion") is not False:
        raise ValueError("Validation completion must not trigger calibration")
    preflight = payload.get("pre_rating_scorability_preflight")
    if (not isinstance(preflight, dict)
            or preflight.get("version") != PREFLIGHT_VERSION
            or tuple(preflight.get("final_queue_ids", [])) != VALIDATION_IDS
            or preflight.get("completed_before_criterion_rating") is not True):
        raise ValueError("Validation artifact is not bound to the frozen scorability preflight")
    if payload.get("status") != "BLOCKED_INSUFFICIENT_SCORABLE_DEVELOPMENT_POOL":
        raise ValueError("Teacher validation must remain blocked until five scorable items exist")
    if payload.get("target_count") != TARGET_COUNT or payload.get("eligible_count") != len(VALIDATION_IDS):
        raise ValueError("Corrected validation queue counts are inconsistent")
    for item in payload["items"]:
        if item.get("split") != "DEVELOPMENT_VALIDATION":
            raise ValueError("Validation item has the wrong split")
        if item.get("audio_source_type") != "RAW_CROPPED":
            raise ValueError("Teacher validation audio must be RAW_CROPPED")
        if item.get("rating_schema_version") != RATING_SCHEMA_VERSION:
            raise ValueError("Validation item schema changed")
        if type(item.get("requires_teacher_scorability_confirmation")) is not bool:
            raise ValueError("Validation scorability policy is missing")
        for label in LABELS:
            value = item.get(label)
            if value is not None and (type(value) is not int or not 1 <= value <= 5):
                raise ValueError("Validation ratings must be null or integers from 1 to 5")


def initialize_validation_rating_artifact(root: Path, destination: Path | None = None) -> dict:
    """Create the separate empty queue once; never merge or overwrite existing ratings."""
    destination = destination or default_artifact_path(root)
    frozen = _assert_frozen_inputs(root)
    if destination.is_file():
        payload = json.loads(destination.read_text(encoding="utf-8"))
        if any("requires_teacher_scorability_confirmation" not in item
               for item in payload.get("items", [])):
            if any(item.get("human_confirmed") for item in payload.get("items", [])):
                raise ValueError("Cannot upgrade scorability policy after validation rating started")
            inputs = json.loads((root /
                "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json").read_text(
                    encoding="utf-8"))
            input_by_id = {item["pair_id"]: item for item in inputs["items"]}
            for item in payload["items"]:
                status = input_by_id[item["pair_id"]].get("scorability_status")
                item["source_scorability_status"] = status
                item["requires_teacher_scorability_confirmation"] = (
                    status == "SCORABLE_AFTER_CANCELLATION"
                )
            _write_rating_atomically_with_snapshot(destination, payload)
        validate_validation_rating_artifact(payload)
        return payload

    split = json.loads((root / "cohort_runs/T001_p14/data_split_v2.json").read_text(
        encoding="utf-8"))
    development, holdout = set(split["development"]), set(split["holdout"])
    if not set(VALIDATION_IDS) <= development or set(VALIDATION_IDS) & holdout:
        raise ValueError("P2.4 validation queue is not development-only")

    manifest = json.loads((root / "cohort_runs/T001_p14/development_manifest_v3.json").read_text(
        encoding="utf-8"))
    manifest_by_id = {item["pair_id"]: item for item in manifest}
    evidence_root = root / "assessment_runs/T001_p24_tournament_v1"
    inputs = json.loads((evidence_root / "validation_inputs_summary.json").read_text(
        encoding="utf-8"))
    input_by_id = {item["pair_id"]: item for item in inputs["items"]}
    if tuple(item["pair_id"] for item in inputs["items"]) != ORIGINAL_IDS:
        raise ValueError("P2.4 machine-input queue does not match the original frozen IDs")

    items = []
    for pair_id in VALIDATION_IDS:
        source = input_by_id[pair_id]
        row = manifest_by_id[pair_id]
        audio_path = evidence_root / source["model_input_ref"]
        if source.get("canonical_source") != "RAW_COMPLETED_DUET" or not audio_path.is_file():
            raise ValueError(f"Missing RAW_CROPPED teacher audio for {pair_id}")
        items.append({
            "pair_id": pair_id,
            "split": "DEVELOPMENT_VALIDATION",
            "quality_gate": row.get("quality_gate"),
            "source_scorability_status": source.get("scorability_status"),
            "requires_teacher_scorability_confirmation": (
                source.get("scorability_status") == "SCORABLE_AFTER_CANCELLATION"
            ),
            "amber_scorability": None,
            "fluency": None,
            "pronunciation": None,
            "intelligibility": None,
            "prosody": None,
            "pronunciation_examples": "",
            "note": "",
            "human_confirmed": False,
            "rated_at_utc": None,
            "rating_schema_version": RATING_SCHEMA_VERSION,
            "audio_source_type": "RAW_CROPPED",
            "canonical_source": "RAW_COMPLETED_DUET",
            "raw_duet_path": row["duet_path"],
            "model_input_ref": source["model_input_ref"],
            "model_input_sha256": source["model_input_sha256"],
            "rater_metadata": {
                "rater_role": "TEACHER_RESEARCH_RATER",
                "human_reviewed": False,
                "ai_assistance_used": True,
            },
        })

    payload = {
        "version": VERSION,
        "rating_schema_version": RATING_SCHEMA_VERSION,
        "status": "BLOCKED_INSUFFICIENT_SCORABLE_DEVELOPMENT_POOL",
        "created_at_utc": now_utc(),
        "split": "DEVELOPMENT_VALIDATION",
        "queue_ids": list(VALIDATION_IDS),
        "target_count": TARGET_COUNT,
        "eligible_count": len(VALIDATION_IDS),
        "criteria": list(LABELS),
        "audio_source_type": "RAW_CROPPED",
        "rater_role": "TEACHER_RESEARCH_RATER",
        "human_reviewed": False,
        "ai_assistance_used": True,
        "p24_frozen_plan_sha256": PLAN_SHA256,
        "p24_winner_freeze_sha256": frozen["winner_sha256"],
        "p24_model_selection_frozen": True,
        "ratings_must_not_reselect_p24_models": True,
        "automatic_calibration_after_completion": False,
        "automatic_merge_into_original_12": False,
        "p25_started": False,
        "holdout_used": False,
        "original_12_ratings_sha256": ORIGINAL_RATINGS_SHA256,
        "pre_rating_scorability_preflight": {
            "version": PREFLIGHT_VERSION,
            "manifest_ref": MANIFEST_NAME,
            "manifest_sha256": frozen["preflight_sha256"],
            "completed_before_rating": True,
            "completed_before_criterion_rating": True,
            "replacement_pool_exhausted": True,
            "final_queue_ids": frozen["preflight"]["final_queue_ids"],
        },
        "technical_exclusions": frozen["preflight"]["technical_exclusions"],
        "items": items,
        "history": [],
    }
    validate_validation_rating_artifact(payload)
    _write_rating_atomically_with_snapshot(destination, payload)
    return payload


def save_validation_rating(path: Path, root: Path, pair_id: str, scorability: str,
                           scores: dict, pronunciation_examples: str = "") -> dict:
    """Refuse rating while the corrected queue has only three eligible items."""
    if pair_id not in VALIDATION_IDS:
        raise ValueError("Only frozen P2.4 development-validation IDs may be rated")
    raise ValueError("Teacher validation is blocked: only 3/5 scorable development items exist")


def rating_progress(payload: dict) -> tuple[int, int]:
    validate_validation_rating_artifact(payload)
    return sum(item.get("human_confirmed") is True for item in payload["items"]), TARGET_COUNT
