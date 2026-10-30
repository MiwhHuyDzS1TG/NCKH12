"""First-class technical scorability and quality-gate decisions."""
from __future__ import annotations

import hashlib
import math
import random


def decide_scorability(alignment_ok: bool, audio_state: str, cancellation: dict | None,
                       learner_duration: float, duet_duration: float,
                       leakage_count: int, overlap_count: int, cfg: dict,
                       contamination_scope: str = "UNKNOWN",
                       has_background_interference: bool = False,
                       has_low_speech_level: bool = False) -> dict:
    reasons = []
    if not alignment_ok:
        return {"scorability_status": "UNSCORABLE_ALIGNMENT", "scorability_confidence": 1.,
                "scorability_reasons": ["Template alignment is unreliable"],
                "quality_gate": "RED", "quality_gate_reasons": ["ALIGNMENT_UNCERTAIN"]}
    fraction = learner_duration/max(duet_duration, 1e-9)
    unusual = fraction < cfg["min_learner_fraction"] or fraction > cfg["max_learner_fraction"]
    if has_background_interference or has_low_speech_level:
        quality_reasons = (["BACKGROUND_INTERFERENCE"] if has_background_interference else []) + (
            ["LOW_SPEECH_LEVEL"] if has_low_speech_level else [])
        descriptions = (["Background audio may mask learner speech"] if has_background_interference else []) + (
            ["Learner speech is too quiet for automatic scoring"] if has_low_speech_level else [])
        return {"scorability_status": "REVIEW_REQUIRED", "scorability_confidence": .85,
                "scorability_reasons": descriptions,
                "quality_gate": "AMBER", "quality_gate_reasons": quality_reasons}
    if contamination_scope == "INTRO_OR_NONSCORING_ONLY":
        reasons = ["UNUSUAL_DURATION"] if unusual else []
        return {"scorability_status": "SCORABLE_CLEAN", "scorability_confidence": .80,
                "scorability_reasons": ["Reference-like audio is outside learner scoring candidates"],
                "quality_gate": "AMBER" if unusual else "GREEN",
                "quality_gate_reasons": reasons}
    if audio_state == "CLEAN_MUTED":
        status = "SCORABLE_CLEAN"
        quality = "AMBER" if unusual else "GREEN"
        if unusual:
            reasons.append("UNUSUAL_DURATION")
        return {"scorability_status": status, "scorability_confidence": .95 if not unusual else .70,
                "scorability_reasons": ["Template audio is absent; raw Duet audio is retained"],
                "quality_gate": quality, "quality_gate_reasons": reasons}
    if audio_state == "REFERENCE_PRESENCE_UNCERTAIN":
        return {"scorability_status": "REVIEW_REQUIRED", "scorability_confidence": .5,
                "scorability_reasons": ["Reference audio presence is uncertain"],
                "quality_gate": "AMBER", "quality_gate_reasons": ["REFERENCE_AUDIO_UNCERTAIN"]}
    cancellation = cancellation or {}
    suppression = cancellation.get("reference_suppression_db", -999.)
    similarity = cancellation.get("residual_reference_similarity", 1.)
    reliable = cancellation.get("status") == "ok"
    if (not reliable or suppression < cfg["min_suppression_db"] or
            similarity is not None and similarity > cfg["max_residual_similarity"]):
        return {"scorability_status": "UNSCORABLE_REFERENCE_OVERLAP", "scorability_confidence": .9,
                "scorability_reasons": ["Strong reference audio remains after available cancellation"],
                "quality_gate": "RED", "quality_gate_reasons": ["WEAK_CANCELLATION"]}
    quality_reasons = []
    if leakage_count:
        quality_reasons.append("REFERENCE_LEAKAGE")
    if overlap_count:
        quality_reasons.append("POSSIBLE_TRUE_OVERLAP")
    if suppression < cfg["green_min_suppression_db"]:
        quality_reasons.append("WEAK_CANCELLATION")
    if unusual:
        quality_reasons.append("UNUSUAL_DURATION")
    return {"scorability_status": "SCORABLE_AFTER_CANCELLATION",
            "scorability_confidence": .85 if quality_reasons else .95,
            "scorability_reasons": ["Reference audio was reduced by a reliable cancellation backend"],
            "quality_gate": "AMBER" if quality_reasons else "GREEN",
            "quality_gate_reasons": quality_reasons}


def deterministic_audit(pair_ids: list[str], fraction: float, minimum: int, seed: int) -> list[str]:
    if not pair_ids:
        return []
    count = min(len(pair_ids), max(minimum if len(pair_ids) >= minimum else len(pair_ids),
                                   int(math.ceil(len(pair_ids)*fraction))))
    rng = random.Random(seed)
    return sorted(rng.sample(sorted(pair_ids), count))


def deterministic_stratified_split(rows: list[dict], holdout_fraction: float,
                                   seed: int) -> dict:
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row.get("audio_state", "UNKNOWN"), []).append(row["pair_id"])
    holdout = []
    for state, pair_ids in sorted(groups.items()):
        ids = sorted(pair_ids)
        rng = random.Random(f"{seed}:{state}")
        rng.shuffle(ids)
        count = max(1, round(len(ids)*holdout_fraction)) if len(ids) > 1 else 0
        holdout.extend(ids[:count])
    holdout = sorted(holdout)
    all_ids = sorted(row["pair_id"] for row in rows)
    return {"seed": seed, "holdout_fraction": holdout_fraction,
            "development": [x for x in all_ids if x not in set(holdout)],
            "holdout": holdout,
            "stratification": "audio_state"}


def deterministic_stratified_split_v2(rows: list[dict], reviewed_ids: set[str],
                                      holdout_fraction: float, seed: int,
                                      target_count: int | None = None) -> dict:
    """Freeze a label-independent split while forcing human-exposed IDs to development."""
    eligible = [row for row in rows if row["pair_id"] not in reviewed_ids]
    target = target_count if target_count is not None else round(len(rows)*holdout_fraction)
    target = min(max(0, target), len(eligible))
    groups: dict[str, list[str]] = {}
    for row in eligible:
        key = f'{row.get("audio_state", "UNKNOWN")}|{row.get("quality_gate", "UNKNOWN")}'
        groups.setdefault(key, []).append(row["pair_id"])
    total = max(1, len(eligible))
    quotas = {key: int(len(ids)*target/total) for key, ids in groups.items()}
    remaining = target-sum(quotas.values())
    order = sorted(groups, key=lambda key: (
        -(len(groups[key])*target/total-quotas[key]),
        hashlib.sha256(f"{seed}:{key}".encode()).hexdigest()))
    for key in order[:remaining]:
        quotas[key] += 1
    holdout: list[str] = []
    for key, pair_ids in sorted(groups.items()):
        ranked = sorted(pair_ids, key=lambda pair_id:
                        hashlib.sha256(f"{seed}:{key}:{pair_id}".encode()).hexdigest())
        holdout.extend(ranked[:quotas[key]])
    holdout = sorted(holdout)
    holdout_set = set(holdout)
    all_ids = sorted(row["pair_id"] for row in rows)
    return {
        "split_version": "P1.4b-v2",
        "seed": seed,
        "holdout_fraction": holdout_fraction,
        "target_holdout_count": target,
        "development": [pair_id for pair_id in all_ids if pair_id not in holdout_set],
        "holdout": holdout,
        "stratification": "frozen_machine_audio_state_x_quality_gate",
        "reviewed_ids_forced_to_development": sorted(reviewed_ids),
    }
