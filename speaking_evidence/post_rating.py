"""Strict one-click gate for the first development-only calibration run.

This module never creates labels and never reads holdout media.  It checks the
fixed split membership, private teacher artifact, and existing development
evidence before delegating to the predeclared P2.2 calibration code.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from speaking_evidence.p22 import (
    DISCLAIMER,
    LABELS,
    RATING_IDS,
    calibrate,
    calibration_readiness,
)
from speaking_evidence.runner import write_json

VERSION = "P2.2C-post-rating-runner-v0.1"


def _read_json(path: Path, reasons: list[str]) -> dict | None:
    if not path.is_file():
        reasons.append(f"Missing required artifact: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        reasons.append(f"Cannot read {path}: {exc}")
        return None
    if not isinstance(value, dict):
        reasons.append(f"Expected a JSON object: {path}")
        return None
    return value


def calibration_preflight(root: Path) -> dict:
    """Return a complete, non-mutating preflight report."""
    root = root.resolve()
    reasons: list[str] = []
    ratings_path = root / "human_ground_truth" / "p22a_v1" / "ratings_v2.json"
    split_path = root / "cohort_runs" / "T001_p14" / "data_split_v2.json"
    target_path = root / "task_profiles" / "T001_target_text_v1.json"
    evidence_root = root / "assessment_runs" / "T001_p22_calibrated_v01"

    ratings_payload = _read_json(ratings_path, reasons)
    split = _read_json(split_path, reasons)
    target = _read_json(target_path, reasons)
    selected = _read_json(evidence_root / "selected_backend_evidence_summary.json", reasons)
    completeness = _read_json(evidence_root / "reading_completeness_summary_v1.json", reasons)

    items = ratings_payload.get("items", []) if ratings_payload else []
    ids = [item.get("pair_id") for item in items if isinstance(item, dict)]
    expected = set(RATING_IDS)
    if ratings_payload:
        if ratings_payload.get("holdout_used") is not False:
            reasons.append("Rating artifact must explicitly say holdout_used=false.")
        if ratings_payload.get("schema_version") != "P2.3-four-criterion-v2":
            reasons.append("The four-criterion ratings_v2 schema is required.")
        if len(ids) != len(set(ids)):
            reasons.append("Duplicate pair IDs exist in the rating queue.")
        if set(ids) != expected:
            reasons.append("Rating queue must contain exactly the frozen 12 development IDs.")

    development = set(split.get("development", [])) if split else set()
    holdout = set(split.get("holdout", [])) if split else set()
    if split:
        if len(development) != 50 or len(holdout) != 18 or development & holdout:
            reasons.append("Fixed split is not the expected disjoint 50 development / 18 holdout split.")
        if not expected <= development or expected & holdout:
            reasons.append("A rating queue ID is outside development or intersects holdout.")

    completed = 0
    scorable: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            reasons.append("Malformed rating row found.")
            continue
        pair_id = item.get("pair_id")
        if item.get("human_confirmed") is not True:
            continue
        completed += 1
        decision = item.get("amber_scorability")
        if item.get("quality_gate") == "AMBER" and decision not in {"SCORABLE", "NOT_SCORABLE"}:
            reasons.append(f"{pair_id}: AMBER needs SCORABLE or NOT_SCORABLE.")
            continue
        if decision == "NOT_SCORABLE":
            continue
        missing = [name for name in LABELS
                   if type(item.get(name)) is not int or not 1 <= item[name] <= 5]
        if missing:
            reasons.append(f"{pair_id}: completed SCORABLE item has invalid/null ratings: {missing}.")
            continue
        scorable.append(item)

        evidence_path = evidence_root / "pairs" / str(pair_id) / "evidence.json"
        evidence = _read_json(evidence_path, reasons)
        if evidence:
            if evidence.get("holdout") is not False or evidence.get("scope") != "DEVELOPMENT_ONLY":
                reasons.append(f"{pair_id}: evidence is not explicitly development-only.")
            if evidence.get("audio_provenance", {}).get("canonical_source") != "RAW_COMPLETED_DUET":
                reasons.append(f"{pair_id}: canonical assessment source is not RAW_COMPLETED_DUET.")

    if completed != len(RATING_IDS):
        reasons.append(f"Teacher queue is incomplete: {completed}/12 confirmed.")

    distributions = {
        label: {str(level): count for level, count in sorted(Counter(
            row[label] for row in scorable
        ).items())}
        for label in LABELS
    }
    readiness = None
    if set(ids) == expected and len(ids) == len(set(ids)):
        try:
            readiness = calibration_readiness(items)
            reasons.extend(reason for reason in readiness["reasons"] if reason not in reasons)
        except ValueError as exc:
            reasons.append(str(exc))

    if target and (target.get("human_confirmed") is not True or not target.get("confirmed_text")):
        reasons.append("T001 target text is not human-confirmed.")
    if selected and selected.get("holdout_processed") is not False:
        reasons.append("Selected-backend evidence does not explicitly exclude holdout.")
    if completeness and (completeness.get("holdout_processed") is not False
                         or completeness.get("score_created") is not False):
        reasons.append("Completeness preparation has an invalid holdout/score state.")

    # Preserve order while removing repeated explanations.
    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "version": VERSION,
        "status": "READY_FOR_DEVELOPMENT_CALIBRATION" if not unique_reasons else "STOPPED",
        "ratings_path": str(ratings_path),
        "completed_count": completed,
        "queue_count": len(items),
        "scorable_count": len(scorable),
        "not_scorable_count": completed - len(scorable),
        "label_distribution": distributions,
        "readiness": readiness,
        "reasons": unique_reasons,
        "holdout_membership_checked_from_frozen_split": True,
        "holdout_media_opened": False,
        "holdout_outcomes_used": False,
        "holdout_media_processed": False,
        "labels": DISCLAIMER,
    }


def run_after_ratings(root: Path) -> dict:
    """Run calibration only after strict preflight passes."""
    root = root.resolve()
    preflight = calibration_preflight(root)
    if preflight["status"] != "READY_FOR_DEVELOPMENT_CALIBRATION":
        return {"version": VERSION, "status": "STOPPED", "preflight": preflight,
                "calibration_created": False, "holdout_processed": False,
                "labels": DISCLAIMER}

    ground = root / "human_ground_truth" / "p22a_v1"
    evidence = root / "assessment_runs" / "T001_p22_calibrated_v01"
    calibration_dir = root / "calibration" / "p22a_v01"
    result = calibrate(
        ground,
        evidence,
        root / "task_profiles" / "T001_target_text_v1.json",
        calibration_dir,
        evidence,
    )
    if result.get("status") != "DEVELOPMENT_PRELIMINARY_CALIBRATION_READY":
        return {"version": VERSION, "status": "STOPPED_AFTER_PREFLIGHT",
                "preflight": preflight, "calibration": result,
                "calibration_created": False, "holdout_processed": False,
                "labels": DISCLAIMER}

    pronunciation_status = {
        "version": VERSION,
        "criterion": "pronunciation",
        "status": "EVIDENCE_ONLY_BACKEND_PENDING",
        "human_label_distribution": preflight["label_distribution"]["pronunciation"],
        "human_calibrated_score": None,
        "backend_status": "BLOCKED_ESPEAK_NG_RUNTIME_FAILURE",
        "reason": (
            "Teacher ratings exist, but the current ASR baseline is not a defensible true "
            "pronunciation model. No proxy score is forced."
        ),
        "holdout_processed": False,
        "labels": DISCLAIMER,
    }
    report_dir = calibration_dir / "criterion_reports_v01"
    write_json(report_dir / "pronunciation_calibration_report_v01.json", pronunciation_status)
    run_summary = {
        "version": VERSION,
        "status": "DEVELOPMENT_PRELIMINARY_CALIBRATION_COMPLETE",
        "preflight": preflight,
        "calibration_status": result["status"],
        "pronunciation_status": pronunciation_status["status"],
        "holdout_processed": False,
        "labels": DISCLAIMER,
    }
    write_json(calibration_dir / "post_rating_run_summary_v01.json", run_summary)
    return run_summary


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = run_after_ratings(root)
    preflight = result["preflight"]
    print("\nP2.2 post-rating calibration preflight")
    print(f"Status: {preflight['status']}")
    print(f"Completed: {preflight['completed_count']}/12")
    print(f"SCORABLE: {preflight['scorable_count']}")
    print("Label distribution:")
    for criterion, distribution in preflight["label_distribution"].items():
        print(f"  - {criterion}: {distribution}")
    if result["status"] == "STOPPED":
        print("\nSTOPPED. No calibrated scores were created:")
        for reason in preflight["reasons"]:
            print(f"  - {reason}")
        return 2
    print("\nDevelopment calibration completed.")
    print("Pronunciation: EVIDENCE_ONLY_BACKEND_PENDING (no forced proxy score).")
    print("Holdout processed: NO")
    print("DEVELOPMENT / PRELIMINARY | NOT CEFR | NOT B2 | NOT IELTS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
