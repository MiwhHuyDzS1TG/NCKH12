"""P2.2A development-only ground truth, completeness, and calibration workflow."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import numpy as np
import yaml

from speaking_evidence.asr import FasterWhisperBackend, validate_words
from speaking_evidence.audio import prepare_turn_audio, sha256_file
from speaking_evidence.p21b import map_profile_to_duet
from speaking_evidence.runner import gate_status, load_development, write_json
from speaking_evidence.wer import word_error_counts, words_for_wer

VERSION = "P2.2A-v0.1"
PREP_VERSION = "P2.2B-PREP-v0.1"
CALIBRATION_REPORT_VERSION = "P2.2C-development-calibration-v0.1"
ASR_AUDIT_IDS = ("T001-D028", "T001-D015", "T001-D068", "T001-D007", "T001-D059", "T001-D005")
GREEN_IDS = ("T001-D005", "T001-D007", "T001-D015", "T001-D028", "T001-D039",
             "T001-D041", "T001-D046", "T001-D059", "T001-D068")
AMBER_IDS = ("T001-D009", "T001-D010", "T001-D034")
RATING_IDS = GREEN_IDS + AMBER_IDS
LABELS = ("fluency", "pronunciation", "intelligibility", "prosody")
DISCLAIMER = ["DEVELOPMENT / PRELIMINARY CALIBRATION", "NOT CEFR", "NOT B2", "NOT IELTS"]
WAITING_FOR_HUMAN_CALIBRATION = "WAITING_FOR_HUMAN_CALIBRATION"
WAITING_FOR_TARGET_CONFIRMATION = "WAITING_FOR_TARGET_CONFIRMATION"
COMPLETENESS_NAME = "ASR-assisted Reading Completeness"
LOW_CONFIDENCE_WORD_THRESHOLD = 0.60


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_target_candidate(template_path: Path, small_path: Path, medium_path: Path,
                           destination: Path) -> dict:
    small = json.loads(small_path.read_text(encoding="utf-8"))
    medium = json.loads(medium_path.read_text(encoding="utf-8"))
    small_text = small["transcript"]["verbatim_transcript"]
    medium_text = medium["transcript"]["verbatim_transcript"]
    agreement = word_error_counts(medium_text, small_text)
    payload = {"version": "T001-target-v1", "template_id": "T001",
               "template_path": "data/templates/T001/original.mp4",
               "template_sha256": sha256_file(template_path),
               "machine_candidate": medium_text, "confirmed_text": None,
               "human_confirmed": False, "status": "CANDIDATE",
               "created_at_utc": now_utc(), "confirmed_at_utc": None,
               "source": {"kind": "TEMPLATE_AUDIO_ASR_CONSENSUS",
                          "candidate_model": medium["model"], "comparison_model": small["model"],
                          "same_text_ignoring_case_punctuation": agreement["wer"] == 0,
                          "cross_model_disagreement": agreement,
                          "audio_preprocessing": "FFmpeg mono 16 kHz PCM16 from T001 template",
                          "visible_text_used": False,
                          "missing_words_invented": False}}
    write_json(destination, payload)
    return payload


def confirm_target(candidate: dict, confirmed_text: str, destination: Path) -> dict:
    if candidate.get("human_confirmed") is not False or candidate.get("status") != "CANDIDATE":
        raise ValueError("Expected an unconfirmed target candidate")
    if not isinstance(confirmed_text, str) or not confirmed_text.strip():
        raise ValueError("Confirmed target text cannot be empty")
    result = copy.deepcopy(candidate)
    result.update({"confirmed_text": confirmed_text, "human_confirmed": True,
                   "status": "HUMAN_CONFIRMED", "confirmed_at_utc": now_utc(),
                   "candidate_sha256": sha256_file(destination)})
    write_json(destination, result)
    return result


def assert_development_ids(rows: list[dict], split: dict, pair_ids: tuple[str, ...]) -> None:
    development, holdout = set(split["development"]), set(split["holdout"])
    if not set(pair_ids) <= development or set(pair_ids) & holdout:
        raise ValueError("P2.2A queue must contain development IDs only")
    by_id = {row["pair_id"]: row for row in rows}
    if any(pid not in by_id for pid in pair_ids) or any(by_id[pid]["quality_gate"] == "RED" for pid in pair_ids):
        raise ValueError("Missing or RED pair in P2.2A queue")


def prepare_workflow(cohort_dir: Path, template_profile_path: Path, template_path: Path,
                     ground_truth_dir: Path, evidence_dir: Path, config_path: Path) -> dict:
    rows, split, manifest_hash = load_development(cohort_dir)
    assert_development_ids(rows, split, RATING_IDS)
    by_id = {row["pair_id"]: row for row in rows}
    profile = json.loads(template_profile_path.read_text(encoding="utf-8"))
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    asr = FasterWhisperBackend(**config["asr"])
    from speaking_evidence.fluency import measure_fluency
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ratings = []
    asr_items = []
    for pair_id in RATING_IDS:
        row = by_id[pair_id]
        mapped = map_profile_to_duet(profile, row)
        turn = mapped["turns"][0]
        pair_dir = evidence_dir / "pairs" / pair_id
        audio_path = pair_dir / "raw_learner_audio.wav"
        audio = prepare_turn_audio(Path(row["duet_path"]), {
            **turn, "learner_intervals": [{"start": max(turn["start_sec"], float(s["start"])),
                                            "end": min(turn["end_sec"], float(s["end"]))}
                                           for s in row["learner_segments"]
                                           if float(s["end"]) > turn["start_sec"] and float(s["start"]) < turn["end_sec"]]},
            audio_path, config["audio"]["sample_rate"])
        intervals = [{"start": max(turn["start_sec"], float(s["start"])),
                      "end": min(turn["end_sec"], float(s["end"]))}
                     for s in row["learner_segments"]
                     if float(s["end"]) > turn["start_sec"] and float(s["start"]) < turn["end_sec"]]
        intervals = [x for x in intervals if x["end"] > x["start"]]
        evidence = {"pair_id": pair_id, "quality_gate": row["quality_gate"],
                    "gate_reasons": row.get("quality_gate_reasons", []),
                    "scorability_status": row["scorability_status"],
                    "raw_duet_path": row["duet_path"], "raw_duet_sha256": sha256_file(Path(row["duet_path"])),
                    "template_path": "data/templates/T001/original.mp4",
                    "template_sha256": sha256_file(template_path),
                    "model_input_ref": str(audio_path.relative_to(evidence_dir)).replace("\\", "/"),
                    "turn": {"start_sec": turn["start_sec"], "end_sec": turn["end_sec"],
                             "learner_intervals": intervals},
                    "canonical_source": "RAW_COMPLETED_DUET",
                    "phase1_manifest_sha256": manifest_hash, "holdout": False}
        write_json(pair_dir / "raw_evidence.json", evidence)
        ratings.append({"pair_id": pair_id, "quality_gate": row["quality_gate"],
                        "amber_scorability": "PENDING" if row["quality_gate"] == "AMBER" else "NOT_REQUIRED",
                        "fluency": None, "intelligibility": None, "prosody": None,
                        "note": "", "human_confirmed": False, "rated_at_utc": None,
                        "raw_evidence_ref": str(pair_dir / "raw_evidence.json").replace("\\", "/")})
        if pair_id in ASR_AUDIT_IDS:
            transcript = asr.transcribe(audio_path, turn["start_sec"], turn["end_sec"], intervals)
            measured = measure_fluency({"start_sec": turn["start_sec"], "end_sec": turn["end_sec"],
                                        "learner_intervals": intervals}, transcript["words"],
                                       config["fluency"]["pause_min_sec"], config["fluency"]["long_pause_sec"])
            record = {"pair_id": pair_id, "status": "UNREVIEWED", "human_confirmed": False,
                      "original_asr": transcript, "human_verbatim_text": None,
                      "model": asr.provenance(), "model_input_ref": evidence["model_input_ref"],
                      "source_audio_sha256": sha256_file(audio_path), "preprocessing": "IDENTICAL_RAW_DUET_DERIVED_16K_MONO_MASKED",
                      "created_at_utc": now_utc(), "confirmed_at_utc": None}
            item_path = ground_truth_dir / "asr_reference_v1" / pair_id / "reference.json"
            write_json(item_path, record)
            asr_items.append({"pair_id": pair_id,
                              "reference_ref": str(item_path).replace("\\", "/"),
                              "measured_speech_rate_wpm": round(60 * len(transcript["words"]) /
                                  max(0.001, turn["end_sec"] - turn["start_sec"]), 2),
                              "measured_pause_ratio": measured["pause_ratio"],
                              "measured_long_pause_count": measured["long_pause_count"],
                              "original_word_count": len(transcript["words"])})
    write_json(ground_truth_dir / "ratings_v1.json",
               {"version": VERSION, "rubric_version": "P22A-rubric-v1", "items": ratings,
                "raw_labels_separate_from_predictions": True, "holdout_used": False})
    write_json(ground_truth_dir / "asr_reference_v1" / "queue.json",
               {"version": VERSION, "selection": "six development videos spanning measured rate/pause behavior",
                "items": asr_items, "holdout_used": False})
    summary = {"version": VERSION, "development_count": len(rows), "holdout_count": len(split["holdout"]),
               "holdout_processed": False, "asr_audit_ids": list(ASR_AUDIT_IDS),
               "rating_ids": list(RATING_IDS), "green_count": len(GREEN_IDS), "amber_count": len(AMBER_IDS),
               "red_count": 0, "asr_backend": asr.provenance(), "no_scores": True,
               "disclaimer": DISCLAIMER}
    write_json(evidence_dir / "workflow_summary.json", summary)
    return summary


def save_asr_reference(path: Path, text: str, confirmed: bool) -> dict:
    record = json.loads(path.read_text(encoding="utf-8"))
    if not confirmed or not isinstance(text, str):
        raise ValueError("Explicit human transcript confirmation is required")
    record.update({"human_verbatim_text": text, "human_confirmed": True,
                   "status": "HUMAN_CONFIRMED", "confirmed_at_utc": now_utc()})
    write_json(path, record)
    return record


def compare_asr_models(ground_truth_dir: Path, evidence_dir: Path, config_path: Path,
                       calibration_dir: Path) -> dict:
    """Compare small/medium only after six actual human references exist."""
    records = {}
    for pair_id in ASR_AUDIT_IDS:
        path = ground_truth_dir / "asr_reference_v1" / pair_id / "reference.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("human_confirmed") is not True:
            raise ValueError(f"Human reference missing: {pair_id}")
        records[pair_id] = record
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["asr"]
    medium = FasterWhisperBackend(**{**config, "model": "medium.en"})
    per_pair = []
    for pair_id in ASR_AUDIT_IDS:
        path = ground_truth_dir / "asr_reference_v1" / pair_id / "reference.json"
        record = records[pair_id]
        raw = json.loads((evidence_dir / "pairs" / pair_id / "raw_evidence.json").read_text(encoding="utf-8"))
        audio_path = evidence_dir / raw["model_input_ref"]
        turn = raw["turn"]
        medium_transcript = medium.transcribe(audio_path, turn["start_sec"], turn["end_sec"],
                                              turn["learner_intervals"])
        validate_words(medium_transcript["words"], turn["start_sec"], turn["end_sec"])
        small_metrics = word_error_counts(record["human_verbatim_text"],
                                          record["original_asr"]["verbatim_transcript"])
        medium_metrics = word_error_counts(record["human_verbatim_text"],
                                           medium_transcript["verbatim_transcript"])
        write_json(path.parent / "medium_transcript.json",
                   {"pair_id": pair_id, "model": medium.provenance(), "transcript": medium_transcript,
                    "model_input_ref": raw["model_input_ref"], "source_audio_sha256": sha256_file(audio_path)})
        per_pair.append({"pair_id": pair_id, "small": small_metrics, "medium": medium_metrics,
                         "small_runtime_sec": record["original_asr"]["runtime_sec"],
                         "medium_runtime_sec": medium_transcript["runtime_sec"],
                         "identical_audio_sha256": sha256_file(audio_path), "word_timestamps_valid": True})
    def aggregate(name: str) -> dict:
        metrics = [p[name] for p in per_pair]
        errors = sum(m["substitutions"] + m["insertions"] + m["deletions"] for m in metrics)
        ref_words = sum(m["reference_words"] for m in metrics)
        wers = [m["wer"] for m in metrics if m["wer"] is not None]
        return {"micro_wer": errors / ref_words if ref_words else None,
                "mean_wer": mean(wers) if wers else None, "median_wer": median(wers) if wers else None,
                "substitutions": sum(m["substitutions"] for m in metrics),
                "insertions": sum(m["insertions"] for m in metrics),
                "deletions": sum(m["deletions"] for m in metrics),
                "runtime_sec": round(sum(p[f"{name}_runtime_sec"] for p in per_pair), 3)}
    small, med = aggregate("small"), aggregate("medium")
    if small["micro_wer"] is None or med["micro_wer"] is None:
        selected, reason = None, "No reference words"
    elif small["micro_wer"] - med["micro_wer"] >= 0.05:
        selected, reason = "medium.en", "Medium reduced micro-WER by at least five percentage points on the six human references"
    else:
        selected, reason = "small.en", "Medium did not reduce micro-WER by five percentage points; small is faster"
    result = {"version": VERSION, "scope": "SIX_HUMAN_REFERENCED_DEVELOPMENT_VIDEOS",
              "per_pair": per_pair, "small.en": small, "medium.en": med,
              "selected_backend": selected, "selection_rule": reason,
              "human_reference_required": True, "holdout_processed": False}
    write_json(calibration_dir / "asr_model_selection_v1.json", result)
    return result


def generate_selected_evidence(ground_truth_dir: Path, evidence_dir: Path, config_path: Path,
                               calibration_dir: Path) -> dict:
    """Run the human-selected ASR backend on the identical 12 saved learner WAVs."""
    selection = json.loads((calibration_dir / "asr_model_selection_v1.json").read_text(encoding="utf-8"))
    selected = selection.get("selected_backend")
    if selected not in {"small.en", "medium.en"}:
        raise ValueError("No ASR backend selected from human-reference WER")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    backend = FasterWhisperBackend(**{**config["asr"], "model": selected})
    from speaking_evidence.acoustic import measure_acoustic
    from speaking_evidence.fluency import aggregate_fluency, measure_fluency
    import soundfile as sf
    produced = []
    for pair_id in RATING_IDS:
        pair_dir = evidence_dir / "pairs" / pair_id
        raw = json.loads((pair_dir / "raw_evidence.json").read_text(encoding="utf-8"))
        audio_path = evidence_dir / raw["model_input_ref"]
        audio, rate = sf.read(audio_path, dtype="float32")
        turn = {"turn_id": "T001", **raw["turn"]}
        transcript = backend.transcribe(audio_path, turn["start_sec"], turn["end_sec"], turn["learner_intervals"])
        fluency = measure_fluency(turn, transcript["words"], config["fluency"]["pause_min_sec"],
                                  config["fluency"]["long_pause_sec"])
        acoustic = measure_acoustic(audio, rate, config["acoustic"]["pitch_floor_hz"],
                                    config["acoustic"]["pitch_ceiling_hz"])
        outcome = {**turn, "model_input_ref": raw["model_input_ref"], "transcript": transcript,
                   "fluency": fluency, "acoustic": acoustic}
        aggregate = aggregate_fluency([{"fluency": fluency}], config["fluency"]["pause_min_sec"],
                                      config["fluency"]["long_pause_sec"])
        evidence = {"version": VERSION, "pair_id": pair_id, "scope": "DEVELOPMENT_ONLY",
                    "quality_gate": raw["quality_gate"], "audio_provenance": raw,
                    "asr_provenance": backend.provenance(), "turns": [outcome],
                    "aggregate_fluency_evidence": aggregate, "no_scores": True,
                    "labels": DISCLAIMER, "holdout": False}
        write_json(pair_dir / "evidence.json", evidence)
        produced.append(pair_id)
    result = {"selected_backend": selected, "processed_ids": produced,
              "holdout_processed": False, "labels": DISCLAIMER}
    write_json(evidence_dir / "selected_backend_evidence_summary.json", result)
    return result


def save_rating(path: Path, pair_id: str, scorability: str, scores: dict, note: str,
                confirmed: bool, pronunciation_examples: str = "",
                rater_metadata: dict | None = None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    item = next(x for x in payload["items"] if x["pair_id"] == pair_id)
    if not confirmed:
        raise ValueError("Explicit human rating confirmation is required")
    if item["quality_gate"] == "AMBER" and scorability not in {"SCORABLE", "NOT_SCORABLE"}:
        raise ValueError("AMBER requires a human scorability decision")
    if scorability == "NOT_SCORABLE":
        scores = {name: None for name in LABELS}
    elif any(type(scores.get(name)) is not int or not 1 <= scores[name] <= 5 for name in LABELS):
        raise ValueError("All four ratings must be integers from 1 to 5")
    if item.get("human_confirmed") is True:
        payload.setdefault("history", []).append({"pair_id": pair_id,
                                                   "superseded_at_utc": now_utc(),
                                                   "previous_rating": copy.deepcopy(item)})
    item.update({**scores, "amber_scorability": scorability if item["quality_gate"] == "AMBER" else "NOT_REQUIRED",
                 "note": note, "pronunciation_examples": pronunciation_examples,
                 "rater_metadata": rater_metadata if rater_metadata is not None else item.get("rater_metadata"),
                 "human_confirmed": True, "rated_at_utc": now_utc()})
    _write_rating_atomically_with_snapshot(path, payload)
    return item


def _write_rating_atomically_with_snapshot(path: Path, payload: dict) -> Path:
    """Commit one human-rating update atomically and retain a private snapshot.

    Rating artifacts live in the ignored human-ground-truth directory.  The
    snapshot is intentionally colocated there so it cannot be published by an
    ordinary Git commit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2,
                            allow_nan=False) + "\n"
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    os.replace(temporary, path)

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_dir = path.parent / "rating_backups"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / f"{path.stem}_{timestamp}_{digest[:12]}.json"
    snapshot.write_text(serialized, encoding="utf-8")
    return snapshot


def align_completeness(target_text: str, learner_text: str, transcript_source: str) -> dict:
    target, learner = words_for_wer(target_text), words_for_wer(learner_text)
    n, m = len(target), len(learner)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = 1 + dp[i+1][j+1] if target[i] == learner[j] else max(dp[i+1][j], dp[i][j+1])
    i = j = 0
    matched = []
    target_matched = set()
    learner_matched = set()
    while i < n and j < m:
        if target[i] == learner[j]:
            matched.append({"word": target[i], "target_index": i, "learner_index": j})
            target_matched.add(i); learner_matched.add(j); i += 1; j += 1
        elif dp[i+1][j] >= dp[i][j+1]:
            i += 1
        else:
            j += 1
    omissions = [{"word": word, "target_index": i} for i, word in enumerate(target) if i not in target_matched]
    insertions = [{"word": word, "learner_index": i} for i, word in enumerate(learner) if i not in learner_matched]
    return {"criterion": COMPLETENESS_NAME,
            "target_words": target, "learner_words": learner, "matched_sequence": matched,
            "omissions": omissions, "insertions": insertions,
            "coverage": len(matched) / len(target) if target else None,
            "transcript_source": transcript_source,
            "warning": "ASR differences are not proven learner reading errors and must not be treated as pronunciation errors"}


def transcript_features(record: dict) -> dict:
    transcript = record["original_asr"]
    probabilities = [w["probability"] for w in transcript["words"] if w.get("probability") is not None]
    segments = transcript.get("segments", [])
    return {"mean_word_probability": mean(probabilities) if probabilities else 0.0,
            "min_word_probability": min(probabilities) if probabilities else 0.0,
            "low_confidence_word_fraction": (
                sum(value < LOW_CONFIDENCE_WORD_THRESHOLD for value in probabilities) / len(probabilities)
                if probabilities else 1.0
            ),
            "mean_segment_logprob": mean(s["avg_logprob"] for s in segments) if segments else -10.0,
            "mean_no_speech_probability": mean(s["no_speech_prob"] for s in segments) if segments else 1.0}


FLUENCY_FEATURES = ("pause_ratio", "long_pause_count", "longest_pause_sec",
                    "mean_length_of_run_words", "speech_rate_wpm", "articulation_rate_wpm", "phonation_ratio")
INTELLIGIBILITY_FEATURES = ("mean_word_probability", "min_word_probability",
                            "low_confidence_word_fraction", "mean_segment_logprob",
                            "mean_no_speech_probability")
PROSODY_FEATURES = ("f0_range_semitones", "f0_std_semitones", "intensity_std_db", "voiced_fraction")


def _rank(values: np.ndarray) -> np.ndarray:
    """Return deterministic average ranks, including ties, without a SciPy dependency."""
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


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3 or len(set(x.tolist())) < 2 or len(set(y.tolist())) < 2:
        return None
    rx, ry = _rank(x), _rank(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def _quadratic_weighted_kappa(human: np.ndarray, predicted: np.ndarray) -> float | None:
    """QWK on rounded 1-5 predictions; undefined cases remain explicit."""
    if len(human) < 3 or len(set(human.tolist())) < 2:
        return None
    observed = np.zeros((5, 5), dtype=float)
    rounded = np.clip(np.rint(predicted), 1, 5).astype(int)
    for left, right in zip(human.astype(int), rounded):
        observed[left - 1, right - 1] += 1
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / max(1, observed.sum())
    weights = np.fromfunction(lambda i, j: ((i - j) ** 2) / 16, (5, 5))
    denominator = float((weights * expected).sum())
    return None if denominator <= 0 else float(1 - (weights * observed).sum() / denominator)


def calibration_readiness(ratings: list[dict]) -> dict:
    """Check the pre-declared gate without inspecting machine/label correlations."""
    unexpected = sorted({row.get("pair_id") for row in ratings} - set(RATING_IDS))
    if unexpected:
        raise ValueError(f"Calibration contains non-development queue IDs: {unexpected}")
    usable = [row for row in ratings
              if row.get("human_confirmed") is True and row.get("amber_scorability") != "NOT_SCORABLE"]
    variation = {
        label: sorted({row.get(label) for row in usable if type(row.get(label)) is int})
        for label in LABELS
    }
    reasons = []
    if len(usable) < 8:
        reasons.append(f"At least 8 SCORABLE human-rated videos are required; available={len(usable)}")
    for label, levels in variation.items():
        if len(levels) < 3:
            reasons.append(f"{label} requires at least 3 distinct human rating levels; available={levels}")
    return {
        "status": "READY_FOR_DEVELOPMENT_CALIBRATION" if not reasons else WAITING_FOR_HUMAN_CALIBRATION,
        "usable_human_ratings": len(usable),
        "required_minimum": 8,
        "label_variation": variation,
        "reasons": reasons,
    }


def generate_completeness_evidence(ground_truth_dir: Path, evidence_dir: Path,
                                   target_path: Path) -> dict:
    """Generate transparent alignment evidence, never a learner score."""
    target = json.loads(target_path.read_text(encoding="utf-8"))
    if target.get("human_confirmed") is not True or not target.get("confirmed_text"):
        return {"version": PREP_VERSION, "criterion": COMPLETENESS_NAME,
                "status": WAITING_FOR_TARGET_CONFIRMATION, "processed_ids": []}
    produced = []
    for pair_id in RATING_IDS:
        pair_dir = evidence_dir / "pairs" / pair_id
        evidence_path = pair_dir / "evidence.json"
        if not evidence_path.is_file():
            raise ValueError(f"Selected-backend evidence missing: {pair_id}")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("holdout") is not False or evidence.get("scope") != "DEVELOPMENT_ONLY":
            raise ValueError(f"Non-development evidence rejected: {pair_id}")
        ref_path = ground_truth_dir / "asr_reference_v1" / pair_id / "reference.json"
        reference = json.loads(ref_path.read_text(encoding="utf-8")) if ref_path.is_file() else None
        if reference and reference.get("human_confirmed") is True:
            learner_text = reference["human_verbatim_text"]
            transcript_source = "HUMAN_VERBATIM"
        else:
            learner_text = evidence["turns"][0]["transcript"]["verbatim_transcript"]
            transcript_source = "SELECTED_ASR_SMALL_EN"
        result = align_completeness(target["confirmed_text"], learner_text, transcript_source)
        result.update({
            "version": PREP_VERSION,
            "status": "EVIDENCE_READY_NO_SCORE",
            "pair_id": pair_id,
            "target_human_confirmed": True,
            "target_version": target.get("version"),
            "target_sha256": target.get("template_sha256"),
            "canonical_audio_source": evidence["audio_provenance"].get("canonical_source"),
            "is_score": False,
        })
        write_json(pair_dir / "reading_completeness_v1.json", result)
        produced.append({"pair_id": pair_id, "coverage": result["coverage"],
                         "transcript_source": transcript_source,
                         "artifact": f"pairs/{pair_id}/reading_completeness_v1.json"})
    summary = {"version": PREP_VERSION, "criterion": COMPLETENESS_NAME,
               "status": "READY", "processed_ids": [item["pair_id"] for item in produced],
               "items": produced, "holdout_processed": False, "score_created": False,
               "warning": "Coverage is ASR-assisted evidence; differences are not proven learner errors."}
    write_json(evidence_dir / "reading_completeness_summary_v1.json", summary)
    return summary


def freeze_machine_features(evidence_dir: Path, destination: Path) -> dict:
    """Freeze pre-declared machine evidence before any teacher ratings are used."""
    specification = {
        "version": PREP_VERSION,
        "frozen_before_human_calibration": True,
        "feature_selection_used_human_labels": False,
        "selection_basis": "pre-declared domain evidence already produced by P2.1/P2.2A",
        "fluency": list(FLUENCY_FEATURES),
        "intelligibility": {
            "mapping_features": list(INTELLIGIBILITY_FEATURES),
            "raw_word_probabilities_preserved": True,
            "low_confidence_threshold": LOW_CONFIDENCE_WORD_THRESHOLD,
            "recognition_stability": "NOT_AVAILABLE_SINGLE_PASS; not invented or used",
        },
        "prosody": {
            "mapping_features": list(PROSODY_FEATURES),
            "descriptive_features": ["f0_median_hz", "f0_p10_hz", "f0_p90_hz",
                                     "intensity_median_db", "pitch_floor_hz", "pitch_ceiling_hz"],
            "backend": "Parselmouth evidence already generated in P2.1",
        },
        "canonical_audio_source_required": "RAW_COMPLETED_DUET",
    }
    rows = []
    for pair_id in RATING_IDS:
        evidence_path = evidence_dir / "pairs" / pair_id / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("holdout") is not False or evidence.get("scope") != "DEVELOPMENT_ONLY":
            raise ValueError(f"Holdout/non-development evidence rejected: {pair_id}")
        if evidence["audio_provenance"].get("canonical_source") != "RAW_COMPLETED_DUET":
            raise ValueError(f"Raw completed Duet is not the canonical source: {pair_id}")
        fluency = evidence["aggregate_fluency_evidence"]
        transcript = evidence["turns"][0]["transcript"]
        acoustic = evidence["turns"][0]["acoustic"]
        probabilities = [word["probability"] for word in transcript.get("words", [])
                         if word.get("probability") is not None]
        intelligibility = transcript_features({"original_asr": transcript})
        rows.append({
            "pair_id": pair_id,
            "source_evidence_sha256": sha256_file(evidence_path),
            "fluency": {name: fluency[name] for name in FLUENCY_FEATURES},
            "intelligibility": {**intelligibility, "word_probabilities": probabilities,
                                  "recognition_stability": None,
                                  "recognition_stability_status": "NOT_AVAILABLE_SINGLE_PASS"},
            "prosody": {name: acoustic.get(name) for name in
                         list(PROSODY_FEATURES) + specification["prosody"]["descriptive_features"]},
        })
    payload = {"version": PREP_VERSION, "status": "FROZEN_PRE_HUMAN_CALIBRATION",
               "created_at_utc": now_utc(), "specification": specification,
               "items": rows, "rating_count_read": 0, "holdout_processed": False}
    write_json(destination, payload)
    return payload


def fit_ridge_mapping(rows: list[dict], label: str, feature_names: tuple[str, ...], alpha: float = 2.0) -> dict:
    """Small deterministic regularized linear mapping with leave-one-out validation."""
    if len(rows) < 8:
        return {"status": "INSUFFICIENT_HUMAN_LABELS", "required": 8, "available": len(rows)}
    y = np.asarray([float(r[label]) for r in rows])
    if len(set(y)) < 3:
        return {"status": "INSUFFICIENT_LABEL_VARIATION", "unique_labels": sorted(set(y.tolist()))}
    x = np.asarray([[float(r[name]) for name in feature_names] for r in rows], dtype=float)
    def fit_predict(train_x, train_y, test_x):
        mu, sd = train_x.mean(axis=0), train_x.std(axis=0)
        sd[sd < 1e-9] = 1.0
        z = (train_x - mu) / sd
        design = np.column_stack([np.ones(len(z)), z])
        penalty = np.eye(design.shape[1]) * alpha; penalty[0, 0] = 0
        beta = np.linalg.solve(design.T @ design + penalty, design.T @ train_y)
        return float(np.clip(np.r_[1.0, (test_x - mu) / sd] @ beta, 1, 5)), mu, sd, beta
    loo = []
    for i in range(len(rows)):
        keep = np.arange(len(rows)) != i
        prediction, _, _, _ = fit_predict(x[keep], y[keep], x[i])
        loo.append(prediction)
    _, mu, sd, beta = fit_predict(x, y, x[0])
    absolute_errors = np.abs(np.asarray(loo) - y)
    predicted_vs_human = [
        {"pair_id": row.get("pair_id", f"row_{index + 1:03d}"),
         "human": int(y[index]), "predicted_loo": round(loo[index], 4),
         "absolute_error": round(float(absolute_errors[index]), 4)}
        for index, row in enumerate(rows)
    ]
    return {"status": "DEVELOPMENT_PRELIMINARY", "model": "ridge_linear_clipped_1_5",
            "alpha": alpha, "features": list(feature_names), "feature_mean": mu.tolist(),
            "feature_scale": sd.tolist(), "intercept": float(beta[0]), "coefficients": beta[1:].tolist(),
            "n": len(rows), "label_distribution": {str(k): int(sum(y == k)) for k in range(1, 6)},
            "validation": "LEAVE_ONE_OUT",
            "loo_mae": float(np.mean(absolute_errors)),
            "within_one_band_agreement": float(np.mean(absolute_errors <= 1.0)),
            "spearman_correlation": _spearman(np.asarray(loo), y),
            "quadratic_weighted_kappa": _quadratic_weighted_kappa(y, np.asarray(loo)),
            "predicted_vs_human": predicted_vs_human,
            "loo_predictions": [round(v, 4) for v in loo],
            "uncertainty": "very small development-only sample; no holdout fitting",
            "labels": DISCLAIMER}


def apply_mapping(mapping: dict, features: dict) -> float | None:
    if mapping.get("status") != "DEVELOPMENT_PRELIMINARY":
        return None
    x = np.asarray([features[name] for name in mapping["features"]], dtype=float)
    z = (x - np.asarray(mapping["feature_mean"])) / np.asarray(mapping["feature_scale"])
    return round(float(np.clip(mapping["intercept"] + z @ np.asarray(mapping["coefficients"]), 1, 5)), 2)


def calibrate(ground_truth_dir: Path, evidence_dir: Path, target_path: Path,
              calibration_dir: Path, output_dir: Path) -> dict:
    target = json.loads(target_path.read_text(encoding="utf-8"))
    if target.get("human_confirmed") is not True:
        raise ValueError("Human-confirmed target text is required")
    ratings_path = (ground_truth_dir / "ratings_v2.json"
                    if (ground_truth_dir / "ratings_v2.json").is_file()
                    else ground_truth_dir / "ratings_v1.json")
    ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
    if ratings_payload.get("holdout_used") is not False:
        raise ValueError("Calibration rating artifact must explicitly exclude holdout")
    ratings = ratings_payload["items"]
    readiness = calibration_readiness(ratings)
    if readiness["status"] != "READY_FOR_DEVELOPMENT_CALIBRATION":
        return {"version": PREP_VERSION, **readiness, "scores": [],
                "holdout_processed": False, "labels": DISCLAIMER}
    usable = [r for r in ratings if r["human_confirmed"] and r["amber_scorability"] != "NOT_SCORABLE"]
    rows = []
    completeness = []
    for rating in usable:
        pair_id = rating["pair_id"]
        evidence_path = evidence_dir / "pairs" / pair_id / "evidence.json"
        if not evidence_path.is_file():
            continue
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if pair_id not in RATING_IDS or evidence.get("holdout") is not False or evidence.get("scope") != "DEVELOPMENT_ONLY":
            raise ValueError(f"Holdout/non-development calibration evidence rejected: {pair_id}")
        if evidence["audio_provenance"].get("canonical_source") != "RAW_COMPLETED_DUET":
            raise ValueError(f"Calibration source is not the raw completed Duet: {pair_id}")
        fluency = evidence["aggregate_fluency_evidence"]
        acoustic = evidence["turns"][0]["acoustic"]
        ref_path = ground_truth_dir / "asr_reference_v1" / pair_id / "reference.json"
        record = json.loads(ref_path.read_text(encoding="utf-8")) if ref_path.is_file() else None
        if record and record.get("human_confirmed"):
            learner_text, source = record["human_verbatim_text"], "HUMAN_VERBATIM"
        else:
            learner_text, source = evidence["turns"][0]["transcript"]["verbatim_transcript"], "SELECTED_ASR_PENDING_VALIDATION"
        prepared_path = output_dir / "pairs" / pair_id / "reading_completeness_v1.json"
        complete = (json.loads(prepared_path.read_text(encoding="utf-8"))
                    if prepared_path.is_file()
                    else align_completeness(target["confirmed_text"], learner_text, source))
        complete["criterion_score_1_5"] = round(1 + 4 * complete["coverage"], 2) if complete["coverage"] is not None else None
        complete["score_mapping"] = "linear endpoints: 0 coverage=1, 1 coverage=5; no proficiency threshold"
        write_json(output_dir / "pairs" / pair_id / "completeness.json", complete)
        completeness.append({"pair_id": pair_id, "coverage": complete["coverage"],
                             "criterion_score_1_5": complete["criterion_score_1_5"], "source": source})
        selected_asr_record = {"original_asr": evidence["turns"][0]["transcript"]}
        rows.append({**rating, **fluency, **transcript_features(selected_asr_record),
                     "completeness_score": complete["criterion_score_1_5"],
                     **{name: acoustic.get(name, 0.0) or 0.0 for name in PROSODY_FEATURES}})
    mappings = {"fluency": fit_ridge_mapping(rows, "fluency", FLUENCY_FEATURES),
                "pronunciation": {"status": "SEPARATE_P23_CALIBRATION_REQUIRED",
                                    "included_in_overall": False,
                                    "reason": "Pronunciation uses separately benchmarked pronunciation evidence; no proxy score is substituted."},
                "intelligibility": fit_ridge_mapping(rows, "intelligibility", INTELLIGIBILITY_FEATURES),
                "prosody": fit_ridge_mapping(rows, "prosody", PROSODY_FEATURES),
                "completeness": {"status": "DEVELOPMENT_PRELIMINARY_DIRECT_EVIDENCE",
                                 "formula": "1 + 4 * target_sequence_coverage",
                                 "range": [1, 5], "thresholds": None,
                                 "warning": "ASR-based coverage is uncertain; human transcript is used where available"}}
    if mappings["prosody"].get("status") == "DEVELOPMENT_PRELIMINARY":
        mappings["prosody"]["included_in_overall"] = False
        mappings["prosody"]["reason"] = "Held separate until acoustic evidence and teacher labels are independently reviewed"
    scores = []
    for row in rows:
        fluency_score = apply_mapping(mappings["fluency"], row)
        intelligibility_score = apply_mapping(mappings["intelligibility"], row)
        completeness_score = row["completeness_score"]
        required = [fluency_score, intelligibility_score, completeness_score]
        overall_ready = all(value is not None for value in required)
        item = {"pair_id": row["pair_id"], "labels": DISCLAIMER,
                "fluency": fluency_score,
                "pronunciation": None,
                "pronunciation_status": "WAITING_FOR_SEPARATE_P23_CALIBRATION",
                "intelligibility": intelligibility_score,
                "completeness": completeness_score,
                "prosody": apply_mapping(mappings["prosody"], row),
                "overall_controlled_reading_score": round(mean(required), 2) if overall_ready else None,
                "overall_components": ["fluency", "intelligibility", "completeness"],
                "overall_formula": "unweighted mean of three validated/preliminary criterion mappings" if overall_ready else None,
                "overall_status": "DEVELOPMENT_PRELIMINARY" if overall_ready else "UNAVAILABLE_INSUFFICIENT_MAPPING"}
        scores.append(item)
    result = {"version": CALIBRATION_REPORT_VERSION,
              "status": "DEVELOPMENT_PRELIMINARY_CALIBRATION_READY",
              "scope": "DEVELOPMENT_ONLY", "n_human_rated": len(rows),
              "mappings": mappings, "completeness_evidence": completeness,
              "scores": scores, "holdout_processed": False, "labels": DISCLAIMER,
              "overall_note": "Overall is emitted only when Fluency, Intelligibility, and Completeness mappings are all available; Prosody remains separate"}
    report_dir = calibration_dir / "criterion_reports_v01"
    for criterion, mapping in mappings.items():
        report = {
            "version": CALIBRATION_REPORT_VERSION,
            "criterion": criterion,
            "scope": "DEVELOPMENT_ONLY",
            "status": mapping.get("status"),
            "mapping": mapping,
            "label_distribution": mapping.get("label_distribution"),
            "sample_size_warning": (
                "Very small development-only sample; results are preliminary and were not fit on holdout."
            ),
            "holdout_processed": False,
            "labels": DISCLAIMER,
        }
        write_json(report_dir / f"{criterion}_calibration_report_v01.json", report)
    write_json(calibration_dir / "criterion_mappings_v01.json", mappings)
    write_json(output_dir / "calibration_summary_v01.json", result)
    write_json(output_dir / "calibration_summary.json", result)
    return result
