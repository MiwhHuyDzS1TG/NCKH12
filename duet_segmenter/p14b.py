"""P1.4b development-only repair after human calibration and Green audit."""
from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import soundfile as sf

from .alignment import build_aligned_reference
from .audibility import contamination_scope, measure_reference_presence
from .pipeline import _write_json, load_config
from .profile import load_template_profile
from .quality import background_interference, measure_audio_quality
from .scorability import deterministic_stratified_split_v2
from .smart_pipeline import _mapped_vad

def human_evidence(root: Path) -> tuple[dict[str, str], dict[str, dict]]:
    """Read human judgments from their saved files, including historical audit notes."""
    calibration = json.loads((root/"calibration_labels.json").read_text(encoding="utf-8"))
    labels = {item["pair_id"]: item["human_label"] for item in calibration["labels"]
              if item.get("human_label") in {"TEMPLATE_AUDIO_MUTED", "TEMPLATE_AUDIO_PRESENT"}}
    audit = json.loads((root/"green_audit.json").read_text(encoding="utf-8"))
    observations = {item["pair_id"]: {"audit": item["audit"],
                   "observation": item.get("reason", "")}
                    for item in audit["items"] if item.get("audit") in {"PASS", "FAIL"}}
    for pair_id, item in observations.items():
        note = item["observation"].lower()
        if item["audit"] == "FAIL" and ("tiếng mẫu" in note or "template voice" in note):
            labels[pair_id] = "TEMPLATE_AUDIO_PRESENT"
    return labels, observations


def reviewed_ids(root: Path) -> set[str]:
    labels, observations = human_evidence(root)
    return set(labels) | set(observations)


def _counts(rows: list[dict]) -> dict:
    count = lambda key: dict(sorted(Counter(row.get(key, "UNKNOWN") for row in rows).items()))
    required = sum(row.get("quality_gate") in {"AMBER", "RED"} for row in rows)
    unusual_only = sum(row.get("quality_gate") == "AMBER" and
                       row.get("quality_gate_reasons") == ["UNUSUAL_DURATION"] for row in rows)
    return {"audio_state_distribution": count("audio_state"),
            "quality_gate_distribution": count("quality_gate"),
            "scorability_distribution": count("scorability_status"),
            "required_human_review": required,
            "amber_unusual_duration_only": unusual_only}


def select_green_audit_v2(rows: list[dict], excluded_ids: set[str], count: int,
                          seed: int) -> list[dict]:
    green = [row for row in rows if row.get("quality_gate") == "GREEN" and
             row["pair_id"] not in excluded_ids]
    risk_count = min(len(green), count//2)
    risky = sorted(green, key=lambda row: (
        -float(row.get("reference_audio_presence_features", {}).get("logmel_similarity_max", 0.)),
        -float(row.get("audio_quality_features", {}).get("background_rms_p90", 0.)),
        row["pair_id"]))[:risk_count]
    selected = {row["pair_id"] for row in risky}
    remainder = [row for row in green if row["pair_id"] not in selected]
    rng = random.Random(seed)
    random_part = rng.sample(sorted(remainder, key=lambda row: row["pair_id"]),
                             min(count-len(risky), len(remainder)))
    items = ([{"pair_id": row["pair_id"], "selection": "BORDERLINE_OR_RISKIER",
               "audit": "UNREVIEWED", "reason": ""} for row in risky] +
             [{"pair_id": row["pair_id"], "selection": "DETERMINISTIC_RANDOM",
               "audit": "UNREVIEWED", "reason": ""} for row in random_part])
    return sorted(items, key=lambda item: item["pair_id"])


def _repair_one(root: Path, pair_id: str, profile, config: dict) -> dict:
    pair_dir = root/"pairs"/pair_id
    old = json.loads((pair_dir/"result.json").read_text(encoding="utf-8"))
    duet, sr = sf.read(pair_dir/"duet_normalized.wav", dtype="float32")
    a, b = old["timeline_mapping"]["a"], old["timeline_mapping"]["b"]
    reference = build_aligned_reference(profile.reference_audio, len(duet), sr, a, b)
    mapped_vad = _mapped_vad(profile.reference_vad, a, b, len(duet)/sr)
    presence = measure_reference_presence(duet, reference, sr, mapped_vad,
                                          config["audio_presence"])
    alignment_ok = old.get("status") == "ok"
    scope = contamination_scope(presence.features, old.get("learner_segments", []),
                                alignment_ok, presence.audio_state)
    quality = measure_audio_quality(duet, sr, old.get("learner_segments", []))
    interference = background_interference(quality, config["audio_quality"])
    repaired = dict(old)
    repaired.update(presence.as_dict())
    repaired.update({"old_audio_state": old.get("audio_state"),
                     "old_reference_audio_presence_score": old.get("reference_audio_presence_score"),
                     "reference_contamination_scope": scope,
                     "audio_quality_features": quality,
                     "background_interference": interference,
                     "p14b_triage_version": "P1.4b-v2"})
    if interference:
        repaired.update({"scorability_status": "REVIEW_REQUIRED",
                         "scorability_confidence": .85,
                         "scorability_reasons": ["Background audio may mask learner speech"],
                         "quality_gate": "AMBER",
                         "quality_gate_reasons": ["BACKGROUND_INTERFERENCE"]})
    elif presence.audio_state != old.get("audio_state") and scope != "INTRO_OR_NONSCORING_ONLY":
        repaired.update({"scorability_status": "REVIEW_REQUIRED",
                         "scorability_confidence": .70,
                         "scorability_reasons": ["V2 found reference-audio evidence requiring a new cancellation review"],
                         "quality_gate": "AMBER",
                         "quality_gate_reasons": ["REFERENCE_AUDIO_UNCERTAIN" if
                            presence.audio_state == "REFERENCE_PRESENCE_UNCERTAIN" else
                            "REFERENCE_AUDIO_PRESENT_REPROCESS_REQUIRED"]})
    _write_json(pair_dir/"reference_audio_presence_v2.json", presence.as_dict() |
                {"reference_contamination_scope": scope})
    _write_json(pair_dir/"audio_quality_v2.json", quality |
                {"background_interference": interference})
    return repaired


def _validation(rows_by_id: dict[str, dict], root: Path) -> dict:
    items = []
    false_clean = false_present = uncertain = 0
    labels, _ = human_evidence(root)
    for pair_id, human in labels.items():
        new = rows_by_id[pair_id]
        old = json.loads((root/"pairs"/pair_id/"result.json").read_text(encoding="utf-8"))
        state = new["audio_state"]
        false_clean += human == "TEMPLATE_AUDIO_PRESENT" and state == "CLEAN_MUTED"
        false_present += human == "TEMPLATE_AUDIO_MUTED" and state == "REFERENCE_PRESENT"
        uncertain += state == "REFERENCE_PRESENCE_UNCERTAIN"
        items.append({
            "pair_id": pair_id, "human_label": human,
            "old_predicted_state": old["audio_state"], "new_predicted_state": state,
            "old_relevant_features": old.get("reference_audio_presence_features", {}),
            "new_relevant_features": new["reference_audio_presence_features"],
            "new_contamination_scope": new["reference_contamination_scope"],
        })
    return {"version": "P1.4b-v2", "items": items,
            "counts": {"false_clean": false_clean, "false_present": false_present,
                       "uncertain": uncertain}}


def _quality_validation(rows_by_id: dict[str, dict], root: Path) -> dict:
    _, observations = human_evidence(root)
    ids = ["T001-D053", "T001-D015", "T001-D032", "T001-D063",
           "T001-D051", "T001-D048"]
    return {"version": "P1.4b-v2", "rule": "loud background AND poor speech/background separation AND tonal background",
            "items": [{"pair_id": pair_id,
                       "human_audit": observations.get(pair_id, {}).get("audit"),
                       "human_observation": observations.get(pair_id, {}).get("observation"),
                       "background_interference": rows_by_id[pair_id]["background_interference"],
                       "features": rows_by_id[pair_id]["audio_quality_features"]}
                      for pair_id in ids]}


def run_p14b(root: str | Path, config: dict | None = None, workers: int = 4) -> dict:
    root = Path(root).resolve()
    config = config or load_config()
    old_rows = json.loads((root/"cohort_manifest.json").read_text(encoding="utf-8"))
    split = deterministic_stratified_split_v2(
        old_rows, reviewed_ids(root), config["cohort"]["holdout_fraction"],
        config["cohort"]["seed"], config["cohort"]["holdout_target_count_v2"])
    _write_json(root/"data_split_v2.json", split)
    development = set(split["development"])
    profile = load_template_profile(root/"template_profile")
    processable = [pair_id for pair_id in sorted(development)
                   if (root/"pairs"/pair_id/"result.json").is_file()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        repaired_rows = list(pool.map(
            lambda pair_id: _repair_one(root, pair_id, profile, config),
            processable))
    old_by_id = {row["pair_id"]: row for row in old_rows}
    for pair_id in sorted(development-set(processable)):
        repaired_rows.append(dict(old_by_id[pair_id]) | {
            "reference_contamination_scope": "UNKNOWN",
            "audio_quality_features": {}, "background_interference": False,
            "p14b_triage_version": "P1.4b-v2"})
    repaired_rows.sort(key=lambda row: row["pair_id"])
    rows_by_id = {row["pair_id"]: row for row in repaired_rows}
    _write_json(root/"development_manifest_v2.json", repaired_rows)
    validation = _validation(rows_by_id, root)
    _write_json(root/"audio_presence_validation.json", validation)
    quality_validation = _quality_validation(rows_by_id, root)
    _write_json(root/"audio_quality_validation.json", quality_validation)
    audit_items = select_green_audit_v2(
        repaired_rows, reviewed_ids(root), config["cohort"]["green_audit_v2_count"],
        config["cohort"]["seed"]+1)
    audit = {"version": "P1.4b-v2", "seed": config["cohort"]["seed"]+1,
             "source": "DEVELOPMENT GREEN ONLY", "items": audit_items,
             "reviewed": 0, "failures": None, "validated": False,
             "status": "PENDING HUMAN AUDIT"}
    _write_json(root/"green_audit_v2.json", audit)
    old_development = [row for row in old_rows if row["pair_id"] in development]
    summary = {
        "version": "P1.4b-v2", "development_count": len(development),
        "holdout_count": len(split["holdout"]), "holdout_ids": split["holdout"],
        "reviewed_ids_in_holdout": sorted(reviewed_ids(root) & set(split["holdout"])),
        "holdout_outcomes_inspected_during_v2_tuning": False,
        "before_development": _counts(old_development),
        "after_development": _counts(repaired_rows),
        "new_green_audit_pair_ids": [item["pair_id"] for item in audit_items],
        "historical_green_audit": {"path": "green_audit.json", "status": "FAILED", "overwritten": False},
        "artifacts_sha256": {},
    }
    after = summary["after_development"]
    summary.update({
        "total_duets": len(repaired_rows),
        "audio_state_distribution": after["audio_state_distribution"],
        "quality_gate_distribution": after["quality_gate_distribution"],
        "scorability_distribution": after["scorability_distribution"],
        "backend_distribution": dict(sorted(Counter(
            row.get("selected_cancellation_backend", "UNKNOWN") for row in repaired_rows).items())),
        "human_review_required_videos": after["required_human_review"],
        "estimated_video_review_reduction": 1-after["required_human_review"]/max(len(repaired_rows), 1),
        "green_audit": {"version": "P1.4b-v2", "seed": audit["seed"],
                        "selected_pair_ids": [item["pair_id"] for item in audit_items],
                        "reviewed": 0, "failures": None, "validated": False,
                        "status": "PENDING HUMAN AUDIT"},
    })
    for name in ("data_split_v2.json", "development_manifest_v2.json",
                 "audio_presence_validation.json", "audio_quality_validation.json",
                 "green_audit_v2.json"):
        summary["artifacts_sha256"][name] = hashlib.sha256((root/name).read_bytes()).hexdigest()
    _write_json(root/"cohort_summary_v2.json", summary)
    return summary
