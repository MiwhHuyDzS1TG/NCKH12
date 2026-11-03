"""Pre-rating technical eligibility audit for the frozen P2.4 validation queue."""
from __future__ import annotations

import hashlib
import json
import math
import wave
from datetime import datetime, timezone
from pathlib import Path

from speaking_evidence.p22 import LABELS, RATING_IDS, _write_rating_atomically_with_snapshot


VERSION = "P2.4-validation-scorability-preflight-v1"
MANIFEST_NAME = "p24_validation_replacement_manifest_v1.json"
ORIGINAL_IDS = (
    "T001-D006",
    "T001-D023",
    "T001-D064",
    "T001-D043",
    "T001-D048",
)
PLAN_SHA256 = "28b2e4ef7c17214c202e09bcc1a5c01c7cecc309a81881c86dec21b81886836a"
SCORABLE_STATUSES = {"SCORABLE_CLEAN", "SCORABLE_AFTER_CANCELLATION"}
RANKING_FEATURES = (
    "learner_duration_sec",
    "scorability_confidence",
    "reference_audio_presence_score",
    "speech_to_background_db",
    "speech_level_dbfs_median",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _rating_gate(root: Path) -> tuple[dict, int]:
    path = root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    payload = _load(path)
    items = payload.get("items", [])
    if tuple(item.get("pair_id") for item in items) != ORIGINAL_IDS:
        raise ValueError("Preflight requires the untouched original five-item queue")
    completed = sum(item.get("human_confirmed") is True for item in items)
    non_null = [
        item.get("pair_id")
        for item in items
        if any(item.get(label) is not None for label in LABELS)
    ]
    if completed or non_null:
        raise ValueError(
            "Validation rating has begun; scorability preflight must not replace queue IDs"
        )
    return payload, completed


def _wav_is_readable(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() > 0 and handle.getframerate() > 0
    except (OSError, EOFError, wave.Error):
        return False


def _turns_valid(item: dict) -> bool:
    turns = item.get("turns")
    if turns is None and isinstance(item.get("turn"), dict):
        turns = [item["turn"]]
    if not isinstance(turns, list) or not turns:
        return False
    previous_end = -1.0
    for turn in turns:
        try:
            start, end = float(turn["start_sec"]), float(turn["end_sec"])
        except (KeyError, TypeError, ValueError):
            return False
        if start < 0 or end <= start or start < previous_end:
            return False
        intervals = turn.get("learner_intervals")
        if not isinstance(intervals, list) or not intervals:
            return False
        interval_end = start
        for interval in intervals:
            try:
                interval_start = float(interval["start"])
                next_end = float(interval["end"])
            except (KeyError, TypeError, ValueError):
                return False
            if interval_start < start or next_end <= interval_start or next_end > end:
                return False
            if interval_start < interval_end:
                return False
            interval_end = next_end
        previous_end = end
    return True


def _machine_features(row: dict) -> dict:
    quality = row.get("audio_quality_features") or {}
    return {
        "learner_duration_sec": row.get("learner_duration_sec"),
        "scorability_confidence": row.get("scorability_confidence"),
        "reference_audio_presence_score": row.get("reference_audio_presence_score"),
        "speech_to_background_db": quality.get("speech_to_background_db"),
        "speech_level_dbfs_median": quality.get("speech_level_dbfs_median"),
    }


def _rank_by_machine_feature_coverage(
    eligible: list[dict], primary_rows: list[dict]
) -> list[dict]:
    """Frozen greedy farthest-first ordering; IDs break exact distance ties."""
    if not eligible:
        return []
    records = [
        {"pair_id": row["pair_id"], "features": _machine_features(row)}
        for row in primary_rows
    ] + eligible
    matrix = [
        [float(item["features"].get(name) or 0.0) for name in RANKING_FEATURES]
        for item in records
    ]
    means = [sum(row[index] for row in matrix) / len(matrix) for index in range(len(RANKING_FEATURES))]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in matrix) / len(matrix)
        scales.append(math.sqrt(variance) if variance > 1e-18 else 1.0)

    normalized = {
        item["pair_id"]: tuple(
            (matrix[row_index][index] - means[index]) / scales[index]
            for index in range(len(RANKING_FEATURES))
        )
        for row_index, item in enumerate(records)
    }
    references = [normalized[row["pair_id"]] for row in primary_rows]
    remaining = {item["pair_id"]: item for item in eligible}
    ranked = []
    while remaining:
        candidates = []
        for pair_id, item in remaining.items():
            point = normalized[pair_id]
            distances = [
                math.sqrt(sum((left - right) ** 2 for left, right in zip(point, ref)))
                for ref in references
            ]
            candidates.append((min(distances, default=0.0), pair_id, item))
        distance, pair_id, item = max(candidates, key=lambda value: (value[0], value[1]))
        ranked.append({
            **item,
            "rank": len(ranked) + 1,
            "distance_from_primary_or_higher_ranked": round(distance, 6),
            "selection_reason": "DETERMINISTIC_GREEDY_MACHINE_FEATURE_COVERAGE",
        })
        references.append(normalized[pair_id])
        del remaining[pair_id]
    return ranked


def _audit_primary(root: Path, pair_id: str, row: dict, source: dict) -> dict:
    input_path = root / "assessment_runs/T001_p24_tournament_v1" / source.get(
        "model_input_ref", ""
    )
    reason_codes = []
    status = row.get("scorability_status")
    gate = row.get("quality_gate")
    if gate == "RED":
        reason_codes.append("P1_RED")
    else:
        reason_codes.append(f"P1_{gate or 'UNKNOWN'}")
    reason_codes.append(f"P1_{status or 'STATUS_MISSING'}")
    if row.get("low_speech_level"):
        reason_codes.append("LOW_SPEECH_LEVEL")
    else:
        reason_codes.append("SPEECH_LEVEL_ACCEPTED_BY_P14C")
    if row.get("background_interference"):
        reason_codes.append("BACKGROUND_INTERFERENCE")
    else:
        reason_codes.append("NO_BACKGROUND_INTERFERENCE_FLAG")
    scope = row.get("reference_contamination_scope")
    if scope == "SCORING_REGION":
        reason_codes.append("REFERENCE_PRESENT_IN_SCORING_REGION")
    elif scope == "NONE":
        reason_codes.append("NO_REFERENCE_CONTAMINATION")
    else:
        reason_codes.append("REFERENCE_SCOPE_UNKNOWN")
    if status == "SCORABLE_AFTER_CANCELLATION":
        reason_codes.append("TEACHER_SCORABILITY_CONFIRMATION_REQUIRED")

    source_ok = source.get("canonical_source") == "RAW_COMPLETED_DUET"
    file_ok = input_path.is_file() and _wav_is_readable(input_path)
    hash_ok = file_ok and _sha256(input_path) == source.get("model_input_sha256")
    turns_ok = _turns_valid(source)
    duration_ok = isinstance(row.get("learner_duration_sec"), (int, float)) and (
        row["learner_duration_sec"] > 0
    )
    for ok, code in (
        (source_ok, "RAW_COMPLETED_DUET_PROVENANCE"),
        (file_ok, "RAW_CROPPED_AUDIO_READABLE"),
        (hash_ok, "RAW_CROPPED_HASH_VERIFIED"),
        (turns_ok, "LEARNER_TIMESTAMPS_VALID"),
        (duration_ok, "LEARNER_SPEECH_DURATION_PRESENT"),
    ):
        reason_codes.append(code if ok else f"FAILED_{code}")

    eligible = (
        gate != "RED"
        and status in SCORABLE_STATUSES
        and source_ok
        and file_ok
        and hash_ok
        and turns_ok
        and duration_ok
    )
    return {
        "pair_id": pair_id,
        "p1_status": gate,
        "scorability": status,
        "p1_confidence": row.get("scorability_confidence"),
        "reason_codes": reason_codes,
        "teacher_rating_eligible": eligible,
        "decision": "KEEP" if eligible else "REPLACE_TECHNICAL_FAILURE",
        "machine_feature_values": _machine_features(row),
        "human_validation_score_used": False,
    }


def build_replacement_manifest(root: Path, destination: Path | None = None) -> dict:
    """Build the audit once, before ratings; never overwrite a frozen manifest."""
    destination = destination or root / MANIFEST_NAME
    if destination.exists():
        payload = _load(destination)
        validate_replacement_manifest(payload)
        return payload

    rating_payload, completed = _rating_gate(root)
    plan_path = root / "pretrained_model_tournament_v1.json"
    if _sha256(plan_path) != PLAN_SHA256:
        raise ValueError("Frozen P2.4 plan hash changed")

    split = _load(root / "cohort_runs/T001_p14/data_split_v2.json")
    development, holdout = set(split["development"]), set(split["holdout"])
    rows = _load(root / "cohort_runs/T001_p14/development_manifest_v3.json")
    row_by_id = {row["pair_id"]: row for row in rows}
    inputs = _load(
        root / "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json"
    )
    input_by_id = {item["pair_id"]: item for item in inputs["items"]}

    preflight = [
        _audit_primary(root, pair_id, row_by_id[pair_id], input_by_id[pair_id])
        for pair_id in ORIGINAL_IDS
    ]
    failed = [item["pair_id"] for item in preflight if not item["teacher_rating_eligible"]]

    excluded = []
    eligible = []
    current = set(ORIGINAL_IDS)
    original_ratings = set(RATING_IDS)
    for row in sorted(rows, key=lambda item: item["pair_id"]):
        pair_id = row["pair_id"]
        reasons = []
        if pair_id in current:
            reasons.append("ORIGINAL_PRIMARY_CANDIDATE")
        if pair_id in original_ratings:
            reasons.append("ORIGINAL_12_CALIBRATION_SET")
        if pair_id not in development:
            reasons.append("NOT_IN_DEVELOPMENT_SPLIT")
        if pair_id in holdout:
            reasons.append("HOLDOUT_EXCLUDED")
        if row.get("quality_gate") == "RED":
            reasons.append("P1_RED")
        if row.get("scorability_status") not in SCORABLE_STATUSES:
            reasons.append(f"P1_{row.get('scorability_status', 'STATUS_MISSING')}")
        if pair_id not in input_by_id:
            reasons.append("NO_FROZEN_RAW_CROPPED_MACHINE_INPUT")
        if reasons:
            excluded.append({"pair_id": pair_id, "reasons": reasons})
        else:
            eligible.append({
                "pair_id": pair_id,
                "features": _machine_features(row),
                "human_validation_score_used": False,
            })

    # The same deterministic feature-space rule as P2.2C is declared and frozen.
    # No candidate currently survives the already-frozen eligibility policy, so
    # there is no safe row to rank or hand-pick.
    ranking = _rank_by_machine_feature_coverage(
        eligible, [row_by_id[pair_id] for pair_id in ORIGINAL_IDS]
    )
    if failed and len(ranking) < len(failed):
        raise ValueError("No eligible deterministic replacement exists for a failed primary")
    replacements = [
        {
            "original_id": failed[index],
            "replacement_id": ranking[index]["pair_id"],
            "reason": "PRE_RATING_TECHNICAL_ELIGIBILITY_REPLACEMENT",
        }
        for index in range(len(failed))
    ]
    replacement_by_id = {item["original_id"]: item["replacement_id"] for item in replacements}
    final_ids = [replacement_by_id.get(pair_id, pair_id) for pair_id in ORIGINAL_IDS]

    payload = {
        "version": VERSION,
        "created_at_utc": _now_utc(),
        "status": "PRE_RATING_SCORABILITY_AUDIT_COMPLETE",
        "ratings_before_audit": f"{completed}/5",
        "original_five_ids": list(ORIGINAL_IDS),
        "preflight": preflight,
        "failed_ids": failed,
        "replacements": replacements,
        "eligible_replacement_pool": eligible,
        "deterministic_backup_ranking": ranking,
        "ranking_policy": "P22C_DETERMINISTIC_MACHINE_FEATURE_COVERAGE_V1",
        "ranking_feature_specification": list(RANKING_FEATURES),
        "ranking_frozen_before_validation_ratings": True,
        "selection_uses_human_validation_scores": False,
        "excluded_candidates": excluded,
        "final_five_ids": final_ids,
        "all_final_items_scorable": not failed or len(replacements) == len(failed),
        "p24_frozen_plan_sha256": PLAN_SHA256,
        "p24_model_selection_unchanged": True,
        "original_12_ratings_sha256": rating_payload["original_12_ratings_sha256"],
        "split_proof": {
            "all_final_in_development": set(final_ids) <= development,
            "final_holdout_intersection": sorted(set(final_ids) & holdout),
            "holdout_count_membership_only": len(holdout),
            "holdout_media_opened": False,
        },
    }
    validate_replacement_manifest(payload)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def validate_replacement_manifest(payload: dict) -> None:
    if payload.get("version") != VERSION:
        raise ValueError("Unexpected validation preflight version")
    if tuple(payload.get("original_five_ids", [])) != ORIGINAL_IDS:
        raise ValueError("Original validation queue changed")
    if payload.get("ratings_before_audit") != "0/5":
        raise ValueError("Preflight was not frozen before validation ratings")
    if payload.get("selection_uses_human_validation_scores") is not False:
        raise ValueError("Replacement selection must be validation-label blind")
    if payload.get("ranking_frozen_before_validation_ratings") is not True:
        raise ValueError("Backup ranking is not frozen before ratings")
    if payload.get("p24_frozen_plan_sha256") != PLAN_SHA256:
        raise ValueError("Frozen P2.4 plan hash changed")
    final_ids = tuple(payload.get("final_five_ids", []))
    if len(final_ids) != 5 or len(set(final_ids)) != 5:
        raise ValueError("Final validation queue must contain five unique IDs")
    if payload.get("all_final_items_scorable") is not True:
        raise ValueError("Final validation queue contains an unscorable item")
    if set(final_ids) & set(RATING_IDS):
        raise ValueError("Final validation queue overlaps the original 12 ratings")
    proof = payload.get("split_proof", {})
    if proof.get("all_final_in_development") is not True or proof.get(
        "final_holdout_intersection"
    ):
        raise ValueError("Final validation queue is not development-only")
    if any(item.get("human_validation_score_used") is not False
           for item in payload.get("preflight", [])):
        raise ValueError("Human validation scores entered the preflight")
    preflight = payload.get("preflight", [])
    if tuple(item.get("pair_id") for item in preflight) != ORIGINAL_IDS:
        raise ValueError("Preflight does not cover the original five in order")
    failed = set(payload.get("failed_ids", []))
    decisions = {item["pair_id"]: item for item in preflight}
    for pair_id, item in decisions.items():
        eligible = item.get("teacher_rating_eligible") is True
        if eligible:
            if (item.get("decision") != "KEEP"
                    or item.get("scorability") not in SCORABLE_STATUSES
                    or item.get("p1_status") == "RED"):
                raise ValueError("A kept validation item is not objectively scorable")
        elif item.get("decision") != "REPLACE_TECHNICAL_FAILURE" or pair_id not in failed:
            raise ValueError("Technical failure is missing replacement provenance")
    replacements = payload.get("replacements", [])
    if {item.get("original_id") for item in replacements} != failed:
        raise ValueError("Failed validation IDs and replacements disagree")
    ranked_ids = [item.get("pair_id") for item in payload.get("deterministic_backup_ranking", [])]
    if any(item.get("replacement_id") not in ranked_ids for item in replacements):
        raise ValueError("A replacement was not drawn from the frozen backup ranking")


def attach_preflight_to_empty_queue(root: Path, manifest_path: Path | None = None) -> dict:
    """Record the frozen audit on the private empty queue without creating a rating."""
    manifest_path = manifest_path or root / MANIFEST_NAME
    manifest = _load(manifest_path)
    validate_replacement_manifest(manifest)
    ratings_path = root / "human_ground_truth/p24_validation_v1/development_validation_ratings_v1.json"
    payload, _ = _rating_gate(root)
    if tuple(manifest["final_five_ids"]) != ORIGINAL_IDS:
        raise ValueError("This version cannot rebuild machine inputs for replacement IDs")
    payload["pre_rating_scorability_preflight"] = {
        "version": VERSION,
        "manifest_ref": MANIFEST_NAME,
        "manifest_sha256": _sha256(manifest_path),
        "completed_before_rating": True,
        "technical_replacements": manifest["replacements"],
        "final_five_ids": manifest["final_five_ids"],
    }
    _write_rating_atomically_with_snapshot(ratings_path, payload)
    return payload
