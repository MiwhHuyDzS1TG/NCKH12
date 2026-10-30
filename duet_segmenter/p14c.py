"""P1.4c development-only low-speech quality repair and human-evidence reuse."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import soundfile as sf

from .cohort import audit_outcome
from .p14b import _counts
from .pipeline import _write_json, load_config
from .quality import background_interference, low_speech_level, measure_audio_quality


def _load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repair_one(root: Path, row: dict, cfg: dict) -> tuple[dict, dict | None]:
    repaired = dict(row)
    pair_id = row["pair_id"]
    audio_path = root/"pairs"/pair_id/"duet_normalized.wav"
    if not audio_path.is_file():
        repaired["low_speech_level"] = False
        return repaired, None
    audio, sr = sf.read(audio_path, dtype="float32")
    quality = measure_audio_quality(audio, sr, row.get("learner_segments", []))
    weak = low_speech_level(quality, cfg)
    interference = background_interference(quality, cfg)
    repaired["audio_quality_features"] = quality
    repaired["background_interference"] = interference
    repaired["low_speech_level"] = weak
    repaired["p14c_triage_version"] = "P1.4c-v3"
    reasons = list(row.get("quality_gate_reasons", []))
    if weak:
        if "LOW_SPEECH_LEVEL" not in reasons:
            reasons.append("LOW_SPEECH_LEVEL")
        if row.get("quality_gate") != "RED":
            repaired["quality_gate"] = "AMBER"
            repaired["scorability_status"] = "REVIEW_REQUIRED"
            repaired["scorability_confidence"] = min(float(row.get("scorability_confidence", 1.)), .85)
            repaired["scorability_reasons"] = list(row.get("scorability_reasons", [])) + [
                "Learner speech is too quiet for automatic scoring"]
    repaired["quality_gate_reasons"] = reasons
    return repaired, quality | {"background_interference": interference,
                                "low_speech_level": weak}


def _past_passes(root: Path) -> dict[str, str]:
    passes = {}
    for name in ("green_audit.json", "green_audit_v2.json"):
        for item in _load(root/name)["items"]:
            if item.get("audit") == "PASS":
                passes[item["pair_id"]] = name
    return passes


def run_p14c(root: str | Path, config: dict | None = None, workers: int = 4) -> dict:
    root = Path(root).resolve()
    config = config or load_config()
    split_path = root/"data_split_v2.json"
    split = _load(split_path)
    development = set(split["development"])
    holdout = set(split["holdout"])
    assert not development & holdout
    v2_rows = _load(root/"development_manifest_v2.json")
    assert {row["pair_id"] for row in v2_rows} == development
    old_audit_hashes = {name: _sha(root/name) for name in
                        ("green_audit.json", "green_audit_v2.json", "calibration_labels.json")}
    split_hash = _sha(split_path)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda row: _repair_one(root, row, config["audio_quality"]), v2_rows))
    rows = []
    for (row, quality), original in zip(results, v2_rows):
        assert row["pair_id"] == original["pair_id"]
        if quality is None and original.get("status") == "ok":
            raise FileNotFoundError(root/"pairs"/row["pair_id"]/"duet_normalized.wav")
        if quality is not None:
            _write_json(root/"pairs"/row["pair_id"]/"audio_quality_v3.json", quality)
        rows.append(row)
    assert {row["pair_id"] for row in rows} == development
    audit_passes = _past_passes(root)
    rows_by_id = {row["pair_id"]: row for row in rows}
    assert rows_by_id["T001-D030"]["quality_gate"] == "AMBER"
    assert rows_by_id["T001-D030"]["scorability_status"] == "REVIEW_REQUIRED"
    assert "LOW_SPEECH_LEVEL" in rows_by_id["T001-D030"]["quality_gate_reasons"]
    assert all(not rows_by_id[pair_id]["low_speech_level"] for pair_id in audit_passes)
    assert rows_by_id["T001-D053"]["background_interference"]
    _write_json(root/"development_manifest_v3.json", rows)

    green = sorted(row["pair_id"] for row in rows if row.get("quality_gate") == "GREEN")
    audit_items = [{"pair_id": pair_id,
                    "audit": "PASS" if pair_id in audit_passes else "UNREVIEWED",
                    "reason": "", "inherited": pair_id in audit_passes,
                    "label_source": audit_passes.get(pair_id)} for pair_id in green]
    audit = {"version": "P1.4c-v3", "source": "CURRENT DEVELOPMENT GREEN ONLY",
             "tolerance": config["cohort"]["green_audit_failure_tolerance"], "items": audit_items}
    audit.update(audit_outcome(audit))
    _write_json(root/"green_audit_v3.json", audit)

    comparisons = sorted((set(audit_passes) | {"T001-D030", "T001-D053"}) & development)
    validation = {"version": "P1.4c-v3",
                  "rule": {key: config["audio_quality"][key] for key in (
                      "low_speech_rms_median_max", "low_speech_rms_p90_max",
                      "low_speech_to_background_db_max")},
                  "items": [{"pair_id": pair_id, "prior_human_audit": (
                      "PASS" if pair_id in audit_passes else "FAIL"),
                      "low_speech_level": rows_by_id[pair_id]["low_speech_level"],
                      "quality_gate": rows_by_id[pair_id]["quality_gate"],
                      "scorability_status": rows_by_id[pair_id]["scorability_status"],
                      "features": rows_by_id[pair_id].get("audio_quality_features", {})}
                      for pair_id in comparisons]}
    _write_json(root/"audio_quality_validation_v3.json", validation)

    v2_summary = _load(root/"cohort_summary_v2.json")
    after = _counts(rows)
    before = _counts(v2_rows)
    summary = {"version": "P1.4c-v3", "development_count": len(rows),
               "holdout_count": len(holdout), "holdout_outcomes_inspected_during_v3_tuning": False,
               "holdout_split_sha256": split_hash, "before_development": before,
               "after_development": after, "total_duets": len(rows),
               "audio_state_distribution": after["audio_state_distribution"],
               "quality_gate_distribution": after["quality_gate_distribution"],
               "scorability_distribution": after["scorability_distribution"],
               "backend_distribution": dict(sorted(Counter(
                   row.get("selected_cancellation_backend", "UNKNOWN") for row in rows).items())),
               "human_review_required_videos": after["required_human_review"],
               "estimated_video_review_reduction": 1-after["required_human_review"]/max(len(rows), 1),
               "current_green_ids": green,
               "inherited_pass_ids": {item["pair_id"]: item["label_source"] for item in audit_items
                                      if item["inherited"]},
               "new_human_queue": [item["pair_id"] for item in audit_items
                                   if item["audit"] == "UNREVIEWED"],
               "green_audit": {"version": "P1.4c-v3", "selected_pair_ids": green,
                               **audit_outcome(audit)},
               "historical_audits_preserved": old_audit_hashes,
               "previous_v2_summary_sha256": _sha(root/"cohort_summary_v2.json"),
               "artifacts_sha256": {}}
    assert v2_summary["development_count"] == summary["development_count"]
    for name in ("development_manifest_v3.json", "audio_quality_validation_v3.json",
                 "green_audit_v3.json"):
        summary["artifacts_sha256"][name] = _sha(root/name)
    _write_json(root/"cohort_summary_v3.json", summary)
    assert _sha(split_path) == split_hash
    assert all(_sha(root/name) == digest for name, digest in old_audit_hashes.items())
    return summary
