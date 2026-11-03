from __future__ import annotations

import hashlib
import json
import math
import re
import wave
from pathlib import Path

import numpy as np

from speaking_evidence.p22 import fit_support_aware_mapping
from speaking_evidence.support_aware import fit_restricted_binary_mapping


VERSION = "P2.4D-MultiPA-v1"
RATED_IDS = (
    "T001-D005", "T001-D007", "T001-D015", "T001-D028",
    "T001-D039", "T001-D041", "T001-D046", "T001-D059",
    "T001-D068", "T001-D009", "T001-D010", "T001-D034",
)
RESERVED_IDS = ("T001-D064", "T001-D043", "T001-D048")
MAX_CHUNK_SEC = 14.5
MIN_ALIGNMENT_CONFIDENCE = 0.45
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _words(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(text)]


def _timed_tokens(asr_words: list[dict]) -> list[dict]:
    """Normalize ASR words while retaining deterministic source-word time bounds."""
    tokens: list[dict] = []
    for source_index, word in enumerate(asr_words):
        pieces = _words(str(word.get("text", "")))
        if not pieces:
            continue
        start = float(word["start_sec"])
        end = float(word["end_sec"])
        width = max(0.0, end - start) / len(pieces)
        for index, piece in enumerate(pieces):
            tokens.append({
                "text": piece,
                "start_sec": start + width * index,
                "end_sec": start + width * (index + 1),
                "source_word_index": source_index,
            })
    return tokens


def _lcs_mapping(target: list[str], learner: list[str]) -> dict[int, int]:
    n, m = len(target), len(learner)
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            table[i][j] = (1 + table[i + 1][j + 1]
                           if target[i] == learner[j]
                           else max(table[i + 1][j], table[i][j + 1]))
    mapping: dict[int, int] = {}
    i = j = 0
    while i < n and j < m:
        if target[i] == learner[j]:
            mapping[j] = i
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return mapping


def segment_closed_response(asr_words: list[dict], confirmed_target: str,
                            maximum_sec: float = MAX_CHUNK_SEC) -> list[dict]:
    """Create frozen <=15 s chunks and assign only human-confirmed target spans."""
    target = _words(confirmed_target)
    learner = _timed_tokens(asr_words)
    if not target or not learner:
        raise ValueError("Target and learner ASR words are required for segmentation")
    mapping = _lcs_mapping(target, [item["text"] for item in learner])
    chunks: list[tuple[int, int]] = []
    first = 0
    while first < len(learner):
        last = first
        while (last + 1 < len(learner)
               and learner[last + 1]["end_sec"] - learner[first]["start_sec"] <= maximum_sec):
            last += 1
        chunks.append((first, last))
        first = last + 1

    result: list[dict] = []
    previous_target_end = -1
    for number, (start_index, end_index) in enumerate(chunks, 1):
        mapped = [mapping[index] for index in range(start_index, end_index + 1)
                  if index in mapping]
        confidence = len(mapped) / (end_index - start_index + 1)
        valid = bool(mapped) and confidence >= MIN_ALIGNMENT_CONFIDENCE
        target_start = min(mapped) if mapped else None
        target_end = max(mapped) if mapped else None
        if target_start is not None and target_start < previous_target_end:
            valid = False
        if valid:
            previous_target_end = int(target_end)
        duration = learner[end_index]["end_sec"] - learner[start_index]["start_sec"]
        result.append({
            "chunk_index": number,
            "learner_token_start": start_index,
            "learner_token_end": end_index,
            "start_sec": round(float(learner[start_index]["start_sec"]), 3),
            "end_sec": round(float(learner[end_index]["end_sec"]), 3),
            "duration_sec": round(float(duration), 3),
            "asr_text": " ".join(item["text"] for item in learner[start_index:end_index + 1]),
            "target_word_start": target_start,
            "target_word_end": target_end,
            "target_text": (" ".join(target[target_start:target_end + 1])
                            if valid else None),
            "alignment_confidence": round(float(confidence), 6),
            "valid_for_scoring": valid,
            "invalid_reason": None if valid else "UNRELIABLE_TARGET_ALIGNMENT_DO_NOT_FABRICATE",
        })
    return result


def write_wav_slice(source: Path, destination: Path, start_sec: float,
                    end_sec: float, padding_sec: float = 0.05) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source), "rb") as reader:
        sample_rate = reader.getframerate()
        start = max(0, int((start_sec - padding_sec) * sample_rate))
        end = min(reader.getnframes(), int((end_sec + padding_sec) * sample_rate))
        if end <= start:
            raise ValueError("Empty WAV slice")
        reader.setpos(start)
        frames = reader.readframes(end - start)
        params = reader.getparams()
    with wave.open(str(destination), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)


def verify_frozen_inputs(root: Path, plan_path: Path) -> tuple[dict, dict, dict]:
    plan = _load(plan_path)
    frozen = plan["frozen_inputs"]
    paths = {
        "teacher_ratings_sha256": root / "human_ground_truth/p22a_v1/ratings_v2.json",
        "p24_winner_freeze_sha256": root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json",
        "target_text_sha256": root / "task_profiles/T001_target_text_v1.json",
        "split_sha256": root / "cohort_runs/T001_p14/data_split_v2.json",
    }
    for key, path in paths.items():
        actual = sha256_file(path)
        if actual != frozen[key]:
            raise ValueError(f"Frozen input changed: {path} ({actual})")
    ratings = _load(paths["teacher_ratings_sha256"])
    target = _load(paths["target_text_sha256"])
    split = _load(paths["split_sha256"])
    if not target.get("human_confirmed") or not target.get("confirmed_text"):
        raise ValueError("Human-confirmed T001 target is required")
    rating_ids = tuple(item["pair_id"] for item in ratings["items"])
    if rating_ids != RATED_IDS:
        raise ValueError(f"Unexpected rating queue/order: {rating_ids}")
    if set(RATED_IDS) & set(split["holdout"]):
        raise ValueError("Holdout ID entered P2.4D")
    if not set(RATED_IDS) <= set(split["development"]):
        raise ValueError("Every P2.4D input must be development")
    return ratings, target, split


def prepare_manifest(root: Path, plan_path: Path, local_root: Path) -> dict:
    ratings, target, _ = verify_frozen_inputs(root, plan_path)
    pair_root = root / "assessment_runs/T001_p22_calibrated_v01/pairs"
    rows = []
    for rating in ratings["items"]:
        pair_id = rating["pair_id"]
        pair_dir = pair_root / pair_id
        raw = _load(pair_dir / "raw_evidence.json")
        evidence = _load(pair_dir / "evidence.json")
        wav = pair_dir / "raw_learner_audio.wav"
        if raw.get("canonical_source") != "RAW_COMPLETED_DUET":
            raise ValueError(f"{pair_id}: raw completed Duet invariant failed")
        if raw.get("holdout") is not False:
            raise ValueError(f"{pair_id}: holdout flag is not false")
        chunks = segment_closed_response(
            evidence["turns"][0]["transcript"]["words"], target["confirmed_text"])
        if not all(chunk["valid_for_scoring"] for chunk in chunks):
            raise ValueError(f"{pair_id}: unreliable target chunk; no text was fabricated")
        for chunk in chunks:
            destination = local_root / "chunks" / pair_id / f"chunk_{chunk['chunk_index']:02d}.wav"
            # The preserved learner WAV is turn-local while evidence timestamps are
            # absolute in the completed Duet timeline.
            audio_offset = float(raw["turn"]["start_sec"])
            local_start = chunk["start_sec"] - audio_offset
            local_end = chunk["end_sec"] - audio_offset
            write_wav_slice(wav, destination, local_start, local_end)
            chunk["wav_path"] = str(destination.resolve())
            chunk["wav_sha256"] = sha256_file(destination)
            chunk["source_wav_time_offset_sec"] = audio_offset
            chunk["source_wav_local_start_sec"] = round(local_start, 3)
            chunk["source_wav_local_end_sec"] = round(local_end, 3)
        rows.append({
            "pair_id": pair_id,
            "raw_audio_sha256": sha256_file(wav),
            "raw_duet_sha256": raw["raw_duet_sha256"],
            "canonical_source": raw["canonical_source"],
            "quality_gate": raw["quality_gate"],
            "scorability_status": raw["scorability_status"],
            "chunks": chunks,
        })
    return {
        "version": VERSION,
        "plan_sha256": sha256_file(plan_path),
        "aggregation": "UNWEIGHTED_MEAN_OF_ALL_VALID_CHUNKS",
        "video_validity": "ALL_PLANNED_CHUNKS_MUST_BE_VALID",
        "items": rows,
        "holdout_processed": False,
        "reserved_validation_ratings_read": False,
    }


def _rank(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2 + 1
        start = end
    return ranks


def correlation(x: list[float], y: list[float], rank: bool = False) -> float | None:
    a, b = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(a) < 3 or float(np.std(a)) < 1e-12 or float(np.std(b)) < 1e-12:
        return None
    if rank:
        a, b = _rank(a), _rank(b)
    return float(np.corrcoef(a, b)[0, 1])


def aggregate_video(chunk_results: list[dict], expected_chunks: int) -> dict:
    valid = [row for row in chunk_results if row.get("valid") is True]
    video_valid = len(valid) == expected_chunks
    fields = ("accuracy", "fluency", "prosody", "total")
    return {
        "valid": video_valid,
        "valid_chunks": len(valid),
        "expected_chunks": expected_chunks,
        "failure_reasons": [row.get("error") for row in chunk_results if not row.get("valid")],
        "raw_pretrained_score": ({field: float(np.mean([row[field] for row in valid]))
                                  for field in fields} if video_valid else None),
        "runtime_sec": float(sum(row.get("runtime_sec", 0.0) for row in chunk_results)),
    }


def direct_metrics(rows: list[dict], human_field: str, machine_field: str) -> dict:
    valid = [row for row in rows if row.get("valid") and row.get(machine_field) is not None]
    human = [float(row[human_field]) for row in valid]
    raw = [float(row[machine_field]) for row in valid]
    mapped = [max(1.0, min(5.0, 1.0 + 0.4 * value)) for value in raw]
    class_means = {
        str(level): float(np.mean([float(row[machine_field]) for row in valid
                                   if float(row[human_field]) == level]))
        for level in sorted(set(human))
    }
    return {
        "n": len(valid),
        "human_support": sorted(set(human)),
        "raw_mean": float(np.mean(raw)) if raw else None,
        "raw_standard_deviation": float(np.std(raw)) if raw else None,
        "pearson": correlation(raw, human),
        "spearman": correlation(raw, human, rank=True),
        "raw_score_mean_by_human_level": class_means,
        "documented_raw_scale_mapping": "clip(1 + 0.4 * raw_0_to_10, 1, 5)",
        "raw_mapped_mae": float(np.mean(np.abs(np.asarray(mapped) - human))) if raw else None,
    }


def calibrate_direct(rows: list[dict], label: str, feature: str) -> dict:
    calibration_rows = [{"pair_id": row["pair_id"], label: int(row[label]), feature: float(row[feature])}
                        for row in rows if row.get("valid") and row.get(feature) is not None]
    support = sorted(set(row[label] for row in calibration_rows))
    if len(calibration_rows) < 10:
        return {"status": "INSUFFICIENT_VALID_MULTIPA_OUTPUT", "n": len(calibration_rows)}
    if len(support) == 2:
        return fit_restricted_binary_mapping(calibration_rows, label, (feature,))
    return fit_support_aware_mapping(calibration_rows, label, (feature,))


def apply_fitted_mapping(mapping: dict, feature_name: str, value: float) -> float | None:
    """Apply the single frozen one-dimensional mapping without changing its support."""
    if mapping.get("status") not in {
        "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED",
        "DEVELOPMENT_PRELIMINARY_MULTI_LEVEL",
    }:
        return None
    if mapping.get("features") != [feature_name]:
        raise ValueError("Only the frozen one-dimensional mapping may be applied")
    standardized = ((float(value) - float(mapping["feature_mean"][0]))
                    / float(mapping["feature_scale"][0]))
    if mapping["model"] == "ridge_regularized_binary_logistic_expected_score":
        linear = float(mapping["intercept"]) + float(mapping["coefficients"][0]) * standardized
        probability = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, linear))))
        low, high = mapping["observed_support"]
        score = low + (high - low) * probability
    else:
        score = float(mapping["intercept"]) + float(mapping["coefficients"][0]) * standardized
        low, high = mapping["output_constraint"]
    return round(max(float(low), min(float(high), float(score))), 4)


def selection_decision(baseline: dict, candidate: dict, valid_count: int,
                       raw_std: float, multi_level: bool = False) -> dict:
    if valid_count < 10 or raw_std < 0.05:
        return {"promote": False, "reason": "MULTIPA_VALIDITY_OR_VARIANCE_GATE_FAILED"}
    allowed = ("DEVELOPMENT_PRELIMINARY_MULTI_LEVEL" if multi_level
               else "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED")
    if candidate.get("status") != allowed:
        return {"promote": False, "reason": "MULTIPA_CALIBRATION_UNSTABLE"}
    mae_gain = float(baseline.get("loo_mae", math.inf)) - float(candidate.get("loo_mae", math.inf))
    if multi_level:
        corr_gain = ((candidate.get("spearman_correlation") or -1.0)
                     - (baseline.get("spearman_correlation") or -1.0))
        promote = mae_gain >= 0.05 or (corr_gain >= 0.10 and candidate["loo_mae"] <= baseline["loo_mae"] + 0.05)
        reason = "FROZEN_MULTI_LEVEL_PROMOTION_RULE_MET" if promote else "BASELINE_RETAINED_BY_FROZEN_RULE"
    else:
        balanced_gain = (float(candidate.get("balanced_accuracy", 0.0))
                         - float(baseline.get("balanced_accuracy", 0.0)))
        promote = mae_gain >= 0.05 or (balanced_gain >= 0.10 and candidate["loo_mae"] <= baseline["loo_mae"] + 0.05)
        reason = "FROZEN_BINARY_PROMOTION_RULE_MET" if promote else "BASELINE_RETAINED_BY_FROZEN_RULE"
    return {"promote": bool(promote), "reason": reason, "loo_mae_gain": mae_gain}


def fallback_decision(valid_videos: int) -> dict:
    """Expose the frozen fallback gate without silently installing/running a model."""
    if valid_videos < 10:
        return {
            "status": "MULTIPA_INSUFFICIENT_VALID_OUTPUT",
            "oollim_evaluation_allowed": True,
            "oollim_autorun": False,
        }
    return {
        "status": "MULTIPA_VALIDITY_GATE_PASSED",
        "oollim_evaluation_allowed": False,
        "oollim_autorun": False,
    }
