"""Same-template cohort pre-scan, triage queues, split, and transparent summary."""
from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Callable

from .pipeline import _write_json
from .profile import build_template_profile, load_template_profile
from .scorability import (deterministic_audit, deterministic_stratified_split,
                          deterministic_stratified_split_v2)
from .smart_pipeline import run_profiled

ANALYSIS_SIGNATURE_VERSION = "P1.4.4-letterbox-normalization-and-visual-consensus"


def _signature(config: dict, profile_hash: str, source: Path) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"))
    stat = source.stat()
    raw = (f"{ANALYSIS_SIGNATURE_VERSION}|{profile_hash}|{payload}|{source.resolve()}|"
           f"{stat.st_size}|{stat.st_mtime_ns}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def cohort_manifest(template_id: str, duet_dir: str | Path) -> list[dict]:
    files = sorted((p for p in Path(duet_dir).iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv"}),
                   key=lambda p: p.name.casefold())
    return [{"pair_id": f"{template_id}-D{index:03d}", "template_id": template_id,
             "duet_path": str(path.resolve()), "learner_alias": None}
            for index, path in enumerate(files, 1)]


def _representatives(rows: list[dict], count: int, clean_limit: float, present_limit: float) -> list[dict]:
    valid = [row for row in rows if row.get("reference_audio_presence_score") is not None]
    if not valid:
        return []
    ordered = sorted(valid, key=lambda x: x["reference_audio_presence_score"])
    chosen = ordered[:2]+ordered[-2:]
    boundary = sorted(valid, key=lambda x: min(abs(x["reference_audio_presence_score"]-clean_limit),
                                                abs(x["reference_audio_presence_score"]-present_limit)))
    chosen += boundary
    unique = []
    seen = set()
    for row in chosen:
        if row["pair_id"] not in seen:
            unique.append({"pair_id": row["pair_id"], "audio_presence_score": row["reference_audio_presence_score"],
                           "predicted_audio_state": row["audio_state"], "human_label": "UNREVIEWED"})
            seen.add(row["pair_id"])
        if len(unique) >= count:
            break
    return unique


def _summary(rows: list[dict], config: dict) -> dict:
    total = len(rows)
    count = lambda key: dict(Counter(row.get(key, "UNKNOWN") for row in rows))
    green = [row["pair_id"] for row in rows if row.get("quality_gate") == "GREEN"]
    audit_ids = deterministic_audit(green, config["cohort"]["green_audit_fraction"],
                                    config["cohort"]["green_audit_minimum"],
                                    config["cohort"]["seed"])
    review_ids = set(audit_ids) | {row["pair_id"] for row in rows if row.get("quality_gate") in {"AMBER", "RED"}}
    intervals = sum(row.get("suspicious_interval_count", 0) for row in rows
                    if row["pair_id"] in review_ids)
    return {"total_duets": total, "status_distribution": count("status"),
            "audio_state_distribution": count("audio_state"),
            "backend_distribution": count("selected_cancellation_backend"),
            "scorability_distribution": count("scorability_status"),
            "quality_gate_distribution": count("quality_gate"),
            "human_review_required_videos": len(review_ids),
            "human_review_required_intervals": intervals,
            "estimated_video_review_reduction": 1-len(review_ids)/max(total, 1),
            "green_audit": {"seed": config["cohort"]["seed"], "selected_pair_ids": audit_ids,
                            "reviewed": 0, "failures": None, "validated": False,
                            "status": "PENDING HUMAN AUDIT"}}


def audit_outcome(audit: dict) -> dict:
    items = audit.get("items", [])
    reviewed = [item for item in items if item.get("audit") in {"PASS", "FAIL"}]
    failures = sum(item.get("audit") == "FAIL" for item in reviewed)
    complete = bool(items) and len(reviewed) == len(items)
    validated = complete and failures/max(len(reviewed), 1) <= float(audit.get("tolerance", 0.))
    status = "VALIDATED" if validated else ("FAILED" if complete else "PENDING HUMAN AUDIT")
    return {"reviewed": len(reviewed), "failures": failures if reviewed else None,
            "validated": validated, "status": status}


def run_cohort(template_path: str | Path, duet_dir: str | Path, output_dir: str | Path,
               template_id: str, config: dict, force: bool = False,
               progress_callback: Callable[[int, int, str], None] | None = None) -> dict:
    started = time.perf_counter()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous_summary_path = output/"cohort_summary.json"
    previous_summary = (json.loads(previous_summary_path.read_text(encoding="utf-8"))
                        if previous_summary_path.exists() else {})
    profile_dir = output/"template_profile"
    profile = build_template_profile(template_path, profile_dir, template_id, config, force=False)
    config_text = json.dumps(config, sort_keys=True, indent=2, ensure_ascii=False)+"\n"
    (output/"config.json").write_text(config_text, encoding="utf-8")
    config_hash = hashlib.sha256((output/"config.json").read_bytes()).hexdigest()
    manifest = cohort_manifest(template_id, duet_dir)
    _write_json(output/"cohort_manifest_source.json", manifest)
    rows = []
    cached_pairs = 0
    for index, item in enumerate(manifest, 1):
        pair_dir = output/"pairs"/item["pair_id"]
        pair_dir.mkdir(parents=True, exist_ok=True)
        source = Path(item["duet_path"])
        signature = _signature(config, profile.profile["template_sha256"], source)
        result_path = pair_dir/"result.json"
        try:
            used_cache = False
            if result_path.exists() and not force:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("analysis_signature") != signature:
                    result = run_profiled(profile, source, pair_dir, config, item["pair_id"])
                else:
                    used_cache = True
            else:
                result = run_profiled(profile, source, pair_dir, config, item["pair_id"])
            result["analysis_signature"] = signature
            _write_json(result_path, result)
            row = {"pair_id": item["pair_id"], "template_id": template_id,
                   "duet_path": item["duet_path"], "status": result["status"],
                   "visual_match_score": result["visual_alignment"]["visual_match_score"],
                   "template_side": result["visual_alignment"]["template_side"],
                   "audio_state": result["audio_state"],
                   "reference_audio_presence_score": result["reference_audio_presence_score"],
                   "selected_audio_path": result["selected_audio_path"],
                   "selected_cancellation_backend": result["selected_cancellation_backend"],
                   "reference_suppression_db": (result.get("cancellation_diagnostics") or {}).get("reference_suppression_db"),
                   "residual_reference_similarity": (result.get("cancellation_diagnostics") or {}).get("residual_reference_similarity"),
                   "scorability_status": result["scorability_status"],
                   "scorability_reasons": result["scorability_reasons"],
                   "quality_gate": result["quality_gate"],
                   "quality_gate_reasons": result["quality_gate_reasons"],
                   "learner_duration_sec": result["learner_duration_sec"],
                   "interval_count": len(result["learner_segments"]),
                   "leakage_candidate_count": len(result["reference_leakage_candidates"]),
                   "overlap_candidate_count": len(result["overlap_candidates"]),
                   "suspicious_interval_count": len(result["suspicious_intervals"]),
                   "warning_count": len(result["warnings"]), "warnings": result["warnings"],
                   "runtime_sec": result["runtime_sec"]}
        except Exception as exc:
            row = {"pair_id": item["pair_id"], "template_id": template_id,
                   "duet_path": item["duet_path"], "status": "error",
                   "visual_match_score": None, "template_side": None,
                   "audio_state": "UNKNOWN", "reference_audio_presence_score": None,
                   "selected_audio_path": "NONE", "selected_cancellation_backend": "UNSCORABLE",
                   "reference_suppression_db": None, "residual_reference_similarity": None,
                   "scorability_status": "UNSCORABLE_ALIGNMENT", "scorability_reasons": [str(exc)],
                   "quality_gate": "RED", "quality_gate_reasons": ["PROCESSING_FAILURE"],
                   "learner_duration_sec": 0., "interval_count": 0,
                   "leakage_candidate_count": 0, "overlap_candidate_count": 0,
                   "suspicious_interval_count": 0, "warning_count": 1,
                   "warnings": [str(exc)], "runtime_sec": 0.}
            _write_json(pair_dir/"failure.json", row)
        if used_cache:
            cached_pairs += 1
        rows.append(row)
        _write_json(output/"cohort_manifest.json", rows)
        if progress_callback:
            progress_callback(index, len(manifest), item["pair_id"])
    fields = list(rows[0]) if rows else []
    with (output/"cohort_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})
    summary = _summary(rows, config)
    summary["template_id"] = template_id
    summary["template_sha256"] = profile.profile["template_sha256"]
    summary["config_sha256"] = config_hash
    summary["analysis_signature_version"] = ANALYSIS_SIGNATURE_VERSION
    invocation_runtime = time.perf_counter()-started
    prior_full_runtime = (previous_summary.get("full_batch_runtime_sec")
                          if previous_summary.get("analysis_signature_version") == ANALYSIS_SIGNATURE_VERSION
                          else None)
    full_batch_runtime = (invocation_runtime if cached_pairs == 0 else prior_full_runtime)
    summary["runtime_sec"] = full_batch_runtime
    summary["full_batch_runtime_sec"] = full_batch_runtime
    summary["last_invocation_runtime_sec"] = invocation_runtime
    summary["pair_runtime_sum_sec"] = sum(float(row.get("runtime_sec", 0.)) for row in rows)
    summary["cached_pair_count"] = cached_pairs
    summary["processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # Human-exposed IDs can never return to holdout. Legacy artifacts remain historical.
    reviewed_ids: set[str] = set()
    for historical_name, key in (("calibration_labels.json", "labels"),
                                 ("green_audit.json", "items")):
        historical = output/historical_name
        if historical.exists():
            payload = json.loads(historical.read_text(encoding="utf-8"))
            reviewed_ids.update(item["pair_id"] for item in payload.get(key, [])
                                if item.get("human_label", item.get("audit", "UNREVIEWED")) != "UNREVIEWED")
    split = deterministic_stratified_split_v2(
        rows, reviewed_ids, config["cohort"]["holdout_fraction"],
        config["cohort"]["seed"], config["cohort"].get("holdout_target_count_v2"))
    _write_json(output/"data_split_v2.json", split)
    if not (output/"data_split.json").exists():
        _write_json(output/"data_split.json", deterministic_stratified_split(
            rows, config["cohort"]["holdout_fraction"], config["cohort"]["seed"]))
    development_ids = set(split["development"])
    development_rows = [row for row in rows if row["pair_id"] in development_ids]
    development_green = [row["pair_id"] for row in development_rows
                         if row.get("quality_gate") == "GREEN"]
    summary["green_audit"]["selected_pair_ids"] = deterministic_audit(
        development_green, config["cohort"]["green_audit_fraction"],
        config["cohort"].get("green_audit_v2_count", 8), config["cohort"]["seed"]+1)
    selected_labels = _representatives(
        development_rows, config["cohort"]["calibration_sample_count"],
        config["audio_presence"]["clean_muted_max_score"],
        config["audio_presence"]["reference_present_min_score"])
    labels_path = output/"calibration_queue_v2.json"
    existing_labels = {}
    if labels_path.exists():
        previous = json.loads(labels_path.read_text(encoding="utf-8"))
        existing_labels = {item["pair_id"]: item for item in previous.get("labels", [])}
    for item in selected_labels:
        if item["pair_id"] in existing_labels:
            item["human_label"] = existing_labels[item["pair_id"]].get("human_label", "UNREVIEWED")
    calibration = {"status": ("COMPLETE" if selected_labels and all(
        item["human_label"] != "UNREVIEWED" for item in selected_labels) else "PENDING HUMAN LABELS"),
        "labels": selected_labels}
    _write_json(labels_path, calibration)
    audit_path = output/"green_audit_v2.json"
    existing_audit = {}
    if audit_path.exists():
        previous = json.loads(audit_path.read_text(encoding="utf-8"))
        existing_audit = {item["pair_id"]: item for item in previous.get("items", [])}
    audit = {"seed": summary["green_audit"]["seed"],
        "tolerance": config["cohort"]["green_audit_failure_tolerance"],
        "items": [existing_audit.get(x, {"pair_id": x, "audit": "UNREVIEWED", "reason": ""})
                  for x in summary["green_audit"]["selected_pair_ids"]]}
    audit.update(audit_outcome(audit))
    _write_json(audit_path, audit)
    summary["green_audit"].update(audit_outcome(audit))
    _write_json(output/"cohort_summary.json", summary)
    return {"rows": rows, "summary": summary, "split": split,
            "profile_dir": str(profile_dir), "output_dir": str(output)}
