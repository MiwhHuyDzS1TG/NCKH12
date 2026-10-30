"""P2.3 pronunciation evidence preparation and calibration gates.

This module never turns ASR disagreement into a confirmed pronunciation error.
All audio must be derived from the raw completed Duet using Phase-1 timestamps.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
from importlib import metadata
from pathlib import Path
from statistics import mean

import numpy as np

from speaking_evidence.audio import require_raw_source, sha256_file
from speaking_evidence.p22 import (LOW_CONFIDENCE_WORD_THRESHOLD, RATING_IDS,
                                   WAITING_FOR_HUMAN_CALIBRATION,
                                   fit_ridge_mapping, now_utc)
from speaking_evidence.runner import write_json
from speaking_evidence.wer import words_for_wer

VERSION = "P2.3-pronunciation-evidence-v1"
RATING_SCHEMA_VERSION = "P2.3-four-criterion-v2"
OPENPRONOUNCE_VERSION = "0.3.0"
OPENPRONOUNCE_PYPI_COMMIT = "8b1e8a3e49eae92756cf7c8335f00f3917f431b8"
PRONUNCIATION_DISCLAIMER = [
    "DEVELOPMENT / PRELIMINARY HUMAN-CALIBRATED PRONUNCIATION",
    "NOT CEFR",
    "NOT B2",
    "NOT IELTS",
    "NOT A NATIVE-LIKENESS OR ACCENT-REDUCTION SCORE",
]


def create_rating_schema_v2(source: Path, destination: Path) -> dict:
    """Create a compatible four-criterion queue without overwriting v1."""
    if destination.is_file():
        payload = json.loads(destination.read_text(encoding="utf-8"))
        if payload.get("schema_version") != RATING_SCHEMA_VERSION:
            raise ValueError("Existing rating destination has an unexpected schema version")
        return payload
    payload_v1 = json.loads(source.read_text(encoding="utf-8"))
    items = []
    for original in payload_v1["items"]:
        item = dict(original)
        item.setdefault("pronunciation", None)
        item.setdefault("pronunciation_examples", "")
        item.setdefault("rater_metadata", original.get("rater_metadata"))
        item["rating_schema_version"] = RATING_SCHEMA_VERSION
        items.append(item)
    payload = {
        "version": "P2.3-v0.1",
        "schema_version": RATING_SCHEMA_VERSION,
        "rubric_version": "P23-four-criterion-rubric-v1",
        "criteria": ["fluency", "pronunciation", "intelligibility", "prosody"],
        "items": items,
        "raw_labels_separate_from_predictions": True,
        "holdout_used": False,
        "provenance": {
            "source_schema": payload_v1.get("rubric_version"),
            "source_sha256": sha256_file(source),
            "source_preserved": True,
            "created_at_utc": now_utc(),
            "migration_note": "Pronunciation fields initialized to null/empty; no human value invented.",
        },
    }
    write_json(destination, payload)
    return payload


def _learner_tokens(words: list[dict]) -> tuple[list[str], list[int]]:
    tokens, source_indices = [], []
    for source_index, record in enumerate(words):
        for token in words_for_wer(str(record.get("text", ""))):
            tokens.append(token)
            source_indices.append(source_index)
    return tokens, source_indices


def align_target_for_pronunciation(target_text: str, transcript_words: list[dict]) -> dict:
    """Classify target/ASR words with a deterministic edit-distance alignment."""
    target = words_for_wer(target_text)
    learner, learner_sources = _learner_tokens(transcript_words)
    n, m = len(target), len(learner)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            substitution = dp[i - 1][j - 1] + (target[i - 1] != learner[j - 1])
            dp[i][j] = min(substitution, dp[i - 1][j] + 1, dp[i][j - 1] + 1)

    target_records, insertions = [], []
    i, j = n, m
    reversed_ops = []
    while i or j:
        if i and j:
            cost = 0 if target[i - 1] == learner[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                reversed_ops.append(("MATCHED" if cost == 0 else "SUBSTITUTED_OR_UNCERTAIN", i - 1, j - 1))
                i -= 1
                j -= 1
                continue
        if i and dp[i][j] == dp[i - 1][j] + 1:
            reversed_ops.append(("OMITTED", i - 1, None))
            i -= 1
        else:
            reversed_ops.append(("INSERTED", None, j - 1))
            j -= 1

    for status, target_index, learner_index in reversed(reversed_ops):
        if status == "INSERTED":
            source_index = learner_sources[learner_index]
            source = transcript_words[source_index]
            insertions.append({"status": status, "learner_word": learner[learner_index],
                               "learner_index": learner_index, "start_sec": source.get("start_sec"),
                               "end_sec": source.get("end_sec"), "eligible_for_pronunciation": False})
            continue
        record = {"status": status, "target_word": target[target_index],
                  "target_index": target_index,
                  "eligible_for_pronunciation": status == "MATCHED",
                  "pronunciation_error_confirmed": False}
        if learner_index is not None:
            source_index = learner_sources[learner_index]
            source = transcript_words[source_index]
            record.update({"learner_word": learner[learner_index], "learner_index": learner_index,
                           "start_sec": source.get("start_sec"), "end_sec": source.get("end_sec"),
                           "asr_probability": source.get("probability")})
        else:
            record.update({"learner_word": None, "learner_index": None,
                           "start_sec": None, "end_sec": None, "asr_probability": None,
                           "handled_by": "ASR-assisted Reading Completeness",
                           "double_penalty_guard": "NO_PRONUNCIATION_ANALYSIS"})
        target_records.append(record)
    return {
        "algorithm": "DETERMINISTIC_WORD_EDIT_ALIGNMENT_V1",
        "target_word_count": len(target),
        "learner_word_count": len(learner),
        "target_words": target_records,
        "insertions": insertions,
        "status_counts": {name: sum(row["status"] == name for row in target_records)
                          + (len(insertions) if name == "INSERTED" else 0)
                          for name in ("MATCHED", "OMITTED", "INSERTED", "SUBSTITUTED_OR_UNCERTAIN")},
        "warning": "ASR mismatch is uncertainty/completeness evidence, not a confirmed pronunciation error.",
    }


def eligible_runs(alignment: dict, max_audio_gap_sec: float = 0.75) -> list[dict]:
    """Group only adjacent MATCHED words; omitted/uncertain words split runs."""
    runs, current = [], []
    for row in alignment["target_words"]:
        if not row["eligible_for_pronunciation"]:
            if current:
                runs.append(current)
                current = []
            continue
        if current and (row["target_index"] != current[-1]["target_index"] + 1
                        or row["learner_index"] != current[-1]["learner_index"] + 1
                        or float(row["start_sec"]) - float(current[-1]["end_sec"]) > max_audio_gap_sec):
            runs.append(current)
            current = []
        current.append(row)
    if current:
        runs.append(current)
    return [{"expected_text": " ".join(word["target_word"] for word in run),
             "start_sec": run[0]["start_sec"], "end_sec": run[-1]["end_sec"],
             "target_indices": [word["target_index"] for word in run],
             "word_count": len(run)} for run in runs]


def validate_pronunciation_input(evidence: dict, evidence_path: Path, evidence_root: Path) -> Path:
    pair_id = evidence.get("pair_id")
    if pair_id not in RATING_IDS:
        raise ValueError("Pronunciation benchmark accepts only the frozen development rating queue")
    if evidence.get("holdout") is not False or evidence.get("scope") != "DEVELOPMENT_ONLY":
        raise ValueError("Holdout/non-development pronunciation input rejected")
    provenance = evidence.get("audio_provenance", {})
    if provenance.get("canonical_source") != "RAW_COMPLETED_DUET":
        raise ValueError("Pronunciation input must come from RAW_COMPLETED_DUET")
    if provenance.get("holdout") is not False:
        raise ValueError("Pronunciation audio provenance must explicitly exclude holdout")
    audio_path = evidence_root / provenance["model_input_ref"]
    require_raw_source(audio_path)
    name = audio_path.name.lower()
    if "residual" in name or "cancel" in name:
        raise ValueError("Residual/cancelled audio is forbidden for pronunciation")
    if sha256_file(evidence_path) == "":  # pragma: no cover - defensive proof of readable evidence
        raise ValueError("Unreadable evidence")
    return audio_path


def build_asr_pronunciation_baseline(evidence_root: Path, target_path: Path) -> dict:
    """Write recognition-only baseline evidence for all 12 development items."""
    target = json.loads(target_path.read_text(encoding="utf-8"))
    if target.get("human_confirmed") is not True:
        raise ValueError("Human-confirmed target required")
    outputs = []
    for pair_id in RATING_IDS:
        pair_dir = evidence_root / "pairs" / pair_id
        evidence_path = pair_dir / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        audio_path = validate_pronunciation_input(evidence, evidence_path, evidence_root)
        transcript = evidence["turns"][0]["transcript"]
        alignment = align_target_for_pronunciation(target["confirmed_text"], transcript.get("words", []))
        matched = [row for row in alignment["target_words"] if row["status"] == "MATCHED"]
        probabilities = [float(row["asr_probability"]) for row in matched
                         if row.get("asr_probability") is not None]
        word_evidence = []
        for row in alignment["target_words"]:
            word_evidence.append({
                "target_word": row["target_word"], "start_sec": row.get("start_sec"),
                "end_sec": row.get("end_sec"), "expected_pronunciation": None,
                "machine_score_or_evidence": row.get("asr_probability") if row["status"] == "MATCHED" else None,
                "confidence": row.get("asr_probability") if row["status"] == "MATCHED" else None,
                "status": row["status"], "eligible_for_pronunciation": row["eligible_for_pronunciation"],
                "pronunciation_error_confirmed": False,
            })
        result = {
            "version": VERSION,
            "pair_id": pair_id,
            "status": "PRONUNCIATION_EVIDENCE_ONLY",
            "backend": {"name": "faster-whisper-recognition-baseline", **evidence["asr_provenance"],
                        "role": "INTELLIGIBILITY_RECOGNITION_BASELINE_NOT_TRUE_PRONUNCIATION"},
            "audio_provenance": {"canonical_source": "RAW_COMPLETED_DUET",
                                 "phase1_timestamps_used": True,
                                 "model_input_ref": evidence["audio_provenance"]["model_input_ref"],
                                 "model_input_sha256": sha256_file(audio_path), "holdout": False},
            "utterance": {
                "backend_raw_score": None, "mean_pronunciation_evidence": None,
                "low_score_word_ratio": None, "low_score_phone_ratio": None,
                "confidence": None, "valid_analyzed_word_count": len(matched),
                "analyzed_coverage": len(matched) / max(1, alignment["target_word_count"]),
                "runtime_sec": transcript.get("runtime_sec"),
                "recognition_proxy": {
                    "mean_word_probability": mean(probabilities) if probabilities else None,
                    "low_confidence_word_fraction": (
                        sum(value < LOW_CONFIDENCE_WORD_THRESHOLD for value in probabilities) / len(probabilities)
                        if probabilities else None),
                    "target_asr_match_coverage": len(matched) / max(1, alignment["target_word_count"]),
                    "recognition_stability": None,
                    "recognition_stability_status": "NOT_AVAILABLE_SINGLE_PASS",
                },
            },
            "word_evidence": word_evidence,
            "phone_evidence": [],
            "alignment": alignment,
            "eligible_runs": eligible_runs(alignment),
            "diagnostics": {
                "final_consonant_evidence": {"status": "NOT_SUPPORTED_BY_ASR_BASELINE", "candidates": []},
                "low_confidence_word_candidates": [row["target_word"] for row in matched
                    if row.get("asr_probability") is not None
                    and row["asr_probability"] < LOW_CONFIDENCE_WORD_THRESHOLD],
                "stress_evidence": {"status": "NOT_SUPPORTED_BY_ASR_BASELINE"},
            },
            "limitations": [
                "ASR confidence measures recognition, not pronunciation accuracy.",
                "No ASR mismatch is labeled as a confirmed pronunciation error.",
                "Omitted words are excluded from pronunciation analysis and remain Completeness evidence.",
            ],
            "human_calibrated_score": None,
            "labels": PRONUNCIATION_DISCLAIMER,
        }
        destination = pair_dir / "pronunciation_asr_baseline_v1.json"
        write_json(destination, result)
        outputs.append({"pair_id": pair_id, "status": result["status"],
                        "matched_words": len(matched),
                        "artifact": f"pairs/{pair_id}/{destination.name}"})
    summary = {"version": VERSION, "backend": "ASR_RECOGNITION_BASELINE",
               "status": "READY_NO_PRONUNCIATION_SCORE", "items": outputs,
               "processed_ids": [item["pair_id"] for item in outputs],
               "holdout_processed": False, "human_ratings_used": 0}
    write_json(evidence_root / "pronunciation_asr_baseline_summary_v1.json", summary)
    return summary


def probe_openpronounce(espeak_root: Path | None = None, timeout_sec: float = 5.0) -> dict:
    """Probe optional dependencies without loading model weights or breaking the core app."""
    started = time.perf_counter()
    try:
        installed = metadata.version("openpronounce")
    except metadata.PackageNotFoundError:
        return {"status": "OPTIONAL_DEPENDENCY_MISSING", "version": None,
                "runtime_sec": round(time.perf_counter() - started, 3)}
    result = {"status": "DEPENDENCY_READY", "version": installed,
              "pypi_commit": OPENPRONOUNCE_PYPI_COMMIT,
              "models_downloaded_or_loaded": False, "output": None}
    executable = None
    if espeak_root:
        candidates = list(espeak_root.rglob("espeak-ng.exe"))
        executable = candidates[0] if candidates else None
    executable = executable or (Path(shutil.which("espeak-ng")) if shutil.which("espeak-ng") else None)
    if not executable:
        result.update({"status": "BLOCKED_ESPEAK_NG_MISSING",
                       "limitations": ["OpenPronounce phonemization requires eSpeak NG."]})
    else:
        try:
            proc = subprocess.run([str(executable), "--version"], capture_output=True, text=True,
                                  timeout=timeout_sec, check=False)
            if proc.returncode:
                result.update({"status": "BLOCKED_ESPEAK_NG_RUNTIME_FAILURE",
                               "espeak_returncode": proc.returncode,
                               "limitations": ["Extracted eSpeak NG did not execute reliably on this Windows host."]})
            else:
                result["espeak_version"] = (proc.stdout or proc.stderr).strip()
        except subprocess.TimeoutExpired:
            result.update({"status": "BLOCKED_ESPEAK_NG_RUNTIME_TIMEOUT",
                           "limitations": ["eSpeak NG 1.52.0 executable timed out during a version probe."]})
    result["runtime_sec"] = round(time.perf_counter() - started, 3)
    return result


def run_openpronounce_candidate(evidence_root: Path, target_path: Path, pair_id: str,
                                espeak_root: Path | None = None) -> dict:
    """Run the optional dedicated backend on MATCHED runs only, failing closed."""
    if pair_id not in RATING_IDS:
        raise ValueError("OpenPronounce accepts only frozen development queue IDs")
    dependency = probe_openpronounce(espeak_root)
    if dependency["status"] != "DEPENDENCY_READY":
        return {"version": VERSION, "pair_id": pair_id, "backend": "OpenPronounce",
                "status": dependency["status"], "backend_version": dependency.get("version"),
                "output": None, "runtime_sec": dependency.get("runtime_sec"),
                "limitations": dependency.get("limitations", []),
                "optional_backend_failure_is_nonfatal": True, "holdout_processed": False}
    started = time.perf_counter()
    try:
        import soundfile as sf
        from openpronounce import compare_audio_with_text
        if espeak_root:
            from phonemizer.backend.espeak.wrapper import EspeakWrapper
            libraries = list(espeak_root.rglob("libespeak-ng.dll"))
            if not libraries:
                raise RuntimeError("libespeak-ng.dll not found")
            EspeakWrapper.set_library(str(libraries[0]))
        evidence_path = evidence_root / "pairs" / pair_id / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        audio_path = validate_pronunciation_input(evidence, evidence_path, evidence_root)
        target = json.loads(target_path.read_text(encoding="utf-8"))
        if target.get("human_confirmed") is not True:
            raise ValueError("Human-confirmed target required")
        transcript_words = evidence["turns"][0]["transcript"].get("words", [])
        alignment = align_target_for_pronunciation(target["confirmed_text"], transcript_words)
        runs = eligible_runs(alignment)
        audio, sample_rate = sf.read(audio_path, dtype="float32")
        turn_start = float(evidence["turns"][0]["start_sec"])
        raw_runs = []
        for run in runs:
            left = max(0, int((float(run["start_sec"]) - turn_start - 0.08) * sample_rate))
            right = min(len(audio), int((float(run["end_sec"]) - turn_start + 0.08) * sample_rate))
            if right <= left:
                continue
            raw_runs.append({"run": run,
                             "result": compare_audio_with_text(audio[left:right], run["expected_text"],
                                                               sampling_rate=sample_rate, lang="en")})
        weighted = [(float(item["result"].get("score", 0)), item["run"]["word_count"])
                    for item in raw_runs]
        raw_score = (sum(score * weight for score, weight in weighted) / sum(weight for _, weight in weighted)
                     if weighted else None)
        phone_evidence, difficult_words, final_candidates = [], [], []
        for item in raw_runs:
            run = item["run"]
            for error in item["result"].get("differences", {}).get("errors", []):
                difficult_words.append({"word": error.get("word"), "expected": error.get("expected"),
                                        "heard": error.get("actual"), "confidence": error.get("confidence")})
                phones = error.get("phones") or []
                for index, phone in enumerate(phones):
                    record = {"target_word": error.get("word"), "expected_phone": phone.get("expected"),
                              "observed_phone": phone.get("heard"), "score_or_evidence": None,
                              "confidence": phone.get("confidence"), "status": "BACKEND_CANDIDATE_EVIDENCE"}
                    phone_evidence.append(record)
                    if index == len(phones) - 1 and phone.get("expected") != phone.get("heard") \
                            and float(phone.get("confidence") or 0) >= 0.5:
                        final_candidates.append(record)
        matched = [row for row in alignment["target_words"] if row["status"] == "MATCHED"]
        result = {
            "version": VERSION, "pair_id": pair_id, "status": "BACKEND_READY",
            "backend": {"name": "OpenPronounce", "version": OPENPRONOUNCE_VERSION,
                        "model": "facebook/wav2vec2-large-960h + facebook/wav2vec2-lv-60-espeak-cv-ft",
                        "role": "DEDICATED_PRONUNCIATION_CANDIDATE_NOT_GROUND_TRUTH"},
            "audio_provenance": {"canonical_source": "RAW_COMPLETED_DUET",
                                 "phase1_timestamps_used": True,
                                 "model_input_ref": evidence["audio_provenance"]["model_input_ref"],
                                 "model_input_sha256": sha256_file(audio_path), "holdout": False},
            "utterance": {"backend_raw_score": raw_score,
                          "mean_pronunciation_evidence": raw_score,
                          "low_score_word_ratio": len(difficult_words) / max(1, len(matched)),
                          "low_score_phone_ratio": None, "confidence": None,
                          "valid_analyzed_word_count": sum(run["word_count"] for run in runs),
                          "analyzed_coverage": len(matched) / max(1, alignment["target_word_count"]),
                          "runtime_sec": round(time.perf_counter() - started, 3)},
            "word_evidence": [{"target_word": row["target_word"], "start_sec": row.get("start_sec"),
                               "end_sec": row.get("end_sec"), "expected_pronunciation": None,
                               "machine_score_or_evidence": None, "confidence": None,
                               "status": row["status"],
                               "eligible_for_pronunciation": row["eligible_for_pronunciation"],
                               "pronunciation_error_confirmed": False}
                              for row in alignment["target_words"]],
            "phone_evidence": phone_evidence,
            "alignment": alignment, "eligible_runs": runs,
            "diagnostics": {"difficult_word_candidates": difficult_words,
                            "final_consonant_evidence": {"status": "BACKEND_CANDIDATE_EVIDENCE",
                                                         "candidates": final_candidates},
                            "stress_evidence": {"status": "NOT_EXPOSED_BY_BACKEND"}},
            "limitations": ["Raw OpenPronounce score requires calibration to NCKH12 teacher ratings.",
                            "Phone recognizer errors and child/accent/noise sensitivity can create false alarms.",
                            "Only MATCHED target/ASR runs were analyzed; omissions were not penalized again."],
            "human_calibrated_score": None, "labels": PRONUNCIATION_DISCLAIMER,
            "raw_backend_runs": raw_runs,
        }
        write_json(evidence_root / "pairs" / pair_id / "pronunciation_openpronounce_v1.json", result)
        return result
    except Exception as exc:  # optional backend must never break the core workflow
        return {"version": VERSION, "pair_id": pair_id, "backend": "OpenPronounce",
                "backend_version": OPENPRONOUNCE_VERSION, "status": "BACKEND_FAILED",
                "output": None, "runtime_sec": round(time.perf_counter() - started, 3),
                "limitations": [f"Optional backend failure: {type(exc).__name__}: {exc}"],
                "optional_backend_failure_is_nonfatal": True, "holdout_processed": False}


def pronunciation_calibration_readiness(ratings: list[dict]) -> dict:
    unexpected = sorted({row.get("pair_id") for row in ratings} - set(RATING_IDS))
    if unexpected:
        raise ValueError(f"Pronunciation calibration contains holdout/non-queue IDs: {unexpected}")
    usable = [row for row in ratings if row.get("human_confirmed") is True
              and row.get("amber_scorability") != "NOT_SCORABLE"
              and isinstance(row.get("pronunciation"), int)]
    labels = sorted({row["pronunciation"] for row in usable})
    reasons = []
    if len(usable) < 8:
        reasons.append(f"At least 8 SCORABLE Pronunciation ratings required; available={len(usable)}")
    if len(labels) < 3:
        reasons.append(f"At least 3 distinct Pronunciation levels required; available={labels}")
    return {"status": "READY" if not reasons else WAITING_FOR_HUMAN_CALIBRATION,
            "usable_human_ratings": len(usable), "label_variation": labels, "reasons": reasons}


def quadratic_weighted_kappa(human: list[int], predicted: list[float]) -> float | None:
    if len(human) < 3 or len(set(human)) < 2:
        return None
    observed = np.zeros((5, 5), dtype=float)
    rounded = [int(np.clip(round(value), 1, 5)) for value in predicted]
    for left, right in zip(human, rounded):
        observed[left - 1, right - 1] += 1
    hist_left = observed.sum(axis=1)
    hist_right = observed.sum(axis=0)
    expected = np.outer(hist_left, hist_right) / max(1, observed.sum())
    weights = np.fromfunction(lambda i, j: ((i - j) ** 2) / 16, (5, 5))
    denominator = float((weights * expected).sum())
    return None if denominator <= 0 else float(1 - (weights * observed).sum() / denominator)


def calibrate_pronunciation_rows(rows: list[dict], feature_names: tuple[str, ...]) -> dict:
    """Prepared deterministic calibration; callers must pass development-only rows."""
    readiness = pronunciation_calibration_readiness(rows)
    if readiness["status"] != "READY":
        return {**readiness, "scores": [], "holdout_processed": False}
    mapping = fit_ridge_mapping(rows, "pronunciation", feature_names)
    table = mapping.get("predicted_vs_human", [])
    human = [int(row["human"]) for row in table]
    predicted = [float(row["predicted_loo"]) for row in table]
    mapping["quadratic_weighted_kappa"] = quadratic_weighted_kappa(human, predicted)
    mapping["labels"] = PRONUNCIATION_DISCLAIMER
    mapping["sample_size_limitation"] = "Very small development-only sample; no holdout selection."
    return {"status": "DEVELOPMENT_PRELIMINARY_PRONUNCIATION_CALIBRATION",
            "mapping": mapping, "scores": [], "holdout_processed": False}


def pronunciation_intelligibility_relationship(ratings: list[dict]) -> dict:
    """Measure rubric redundancy only after all 12 four-criterion ratings exist."""
    unexpected = sorted({row.get("pair_id") for row in ratings} - set(RATING_IDS))
    if unexpected:
        raise ValueError(f"Relationship analysis contains holdout/non-queue IDs: {unexpected}")
    usable = [row for row in ratings if row.get("human_confirmed") is True
              and row.get("amber_scorability") != "NOT_SCORABLE"
              and isinstance(row.get("pronunciation"), int)
              and isinstance(row.get("intelligibility"), int)]
    if sum(row.get("human_confirmed") is True for row in ratings) < len(RATING_IDS):
        return {"status": WAITING_FOR_HUMAN_CALIBRATION, "available": len(usable),
                "required_completed_queue": len(RATING_IDS), "spearman_correlation": None}
    try:
        from scipy.stats import spearmanr
        correlation = float(spearmanr([row["pronunciation"] for row in usable],
                                      [row["intelligibility"] for row in usable]).statistic)
        if not math.isfinite(correlation):
            correlation = None
    except Exception:
        correlation = None
    return {"status": "MEASURED_DEVELOPMENT_ONLY", "n": len(usable),
            "spearman_correlation": correlation,
            "decision": "Keep both criteria; report redundancy for later rubric review, do not remove automatically.",
            "holdout_processed": False}
