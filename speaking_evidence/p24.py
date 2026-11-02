"""P2.4 pretrained-model tournament with frozen-plan and holdout guards."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import subprocess
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import numpy as np
import psutil

from speaking_evidence.asr import normalize_transcript
from speaking_evidence.audio import prepare_turn_audio, sha256_file
from speaking_evidence.p21b import map_profile_to_duet
from speaking_evidence.p22 import (
    FLUENCY_FEATURES,
    INTELLIGIBILITY_FEATURES,
    PROSODY_FEATURES,
    RATING_IDS,
    align_completeness,
    fit_support_aware_mapping,
    transcript_features,
)
from speaking_evidence.runner import write_json
from speaking_evidence.support_aware import fit_restricted_binary_mapping
from speaking_evidence.wer import word_error_counts, words_for_wer


VERSION = "P2.4-pretrained-model-tournament-v1"
VALIDATION_IDS = ("T001-D006", "T001-D023", "T001-D064", "T001-D043", "T001-D048")
ALL_P24_IDS = RATING_IDS + VALIDATION_IDS
ALLOWED_STATUSES = {
    "SELECTED_PRELIMINARY", "BASELINE_RETAINED", "MACHINE_CALIBRATION_UNSTABLE",
    "EVIDENCE_ONLY", "BACKEND_UNAVAILABLE",
}


def plan_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_plan(path: Path, prior_result: Path | None = None) -> tuple[dict, str]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("status") != "FROZEN_BEFORE_CANDIDATE_BENCHMARK":
        raise ValueError("P2.4 candidate plan must be frozen before benchmarking")
    digest = plan_sha256(path)
    if prior_result and prior_result.is_file():
        previous = json.loads(prior_result.read_text(encoding="utf-8"))
        if previous.get("plan_sha256") != digest:
            raise ValueError("Frozen candidate plan changed after benchmark results existed")
    if tuple(plan["data_policy"]["development_model_validation_set"]) != VALIDATION_IDS:
        raise ValueError("Unexpected P2.4 development validation set")
    if set(plan["data_policy"]["calibration_model_selection_set"]) != set(RATING_IDS):
        raise ValueError("Unexpected P2.4 calibration/model-selection set")
    return plan, digest


class PeakMemoryMonitor:
    """Sample process-tree RSS; VRAM remains null when CUDA runtime is unavailable."""

    def __init__(self, interval_sec: float = 0.05):
        self.interval_sec = interval_sec
        self.peak_rss = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        process = psutil.Process()
        while not self._stop.is_set():
            total = process.memory_info().rss
            for child in process.children(recursive=True):
                try:
                    total += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            self.peak_rss = max(self.peak_rss, total)
            self._stop.wait(self.interval_sec)

    def __enter__(self):
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        return False


def _atomic_json(path: Path, value: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def assert_split_policy(root: Path, ids: tuple[str, ...]) -> dict:
    split = json.loads((root / "cohort_runs/T001_p14/data_split_v2.json").read_text(encoding="utf-8"))
    development, holdout = set(split["development"]), set(split["holdout"])
    if not set(ids) <= development or set(ids) & holdout:
        raise ValueError("P2.4 IDs must be development-only and disjoint from holdout")
    return {
        "development_count": len(development), "holdout_count": len(holdout),
        "requested_ids_in_development": True, "holdout_intersection": [],
        "holdout_media_opened": False, "holdout_outcomes_used": False,
    }


def prepare_validation_inputs(root: Path, output_root: Path) -> dict:
    """Create raw-derived model inputs for the reserved five without ASR or labels."""
    split_proof = assert_split_policy(root, VALIDATION_IDS)
    rows = json.loads((root / "cohort_runs/T001_p14/development_manifest_v3.json").read_text(encoding="utf-8"))
    by_id = {row["pair_id"]: row for row in rows}
    profile = json.loads((root / "task_profiles/T001_v2_ai.json").read_text(encoding="utf-8"))
    items = []
    for pair_id in VALIDATION_IDS:
        row = by_id[pair_id]
        if row.get("quality_gate") == "RED":
            raise ValueError(f"RED item rejected from validation preparation: {pair_id}")
        mapped = map_profile_to_duet(profile, row)
        turn = mapped["turns"][0]
        intervals = [
            {"start": max(turn["start_sec"], float(segment["start"])),
             "end": min(turn["end_sec"], float(segment["end"]))}
            for segment in row["learner_segments"]
            if float(segment["end"]) > turn["start_sec"]
            and float(segment["start"]) < turn["end_sec"]
        ]
        intervals = [interval for interval in intervals if interval["end"] > interval["start"]]
        prepared_turn = {**turn, "learner_intervals": intervals}
        destination = output_root / "validation_inputs" / pair_id / "raw_learner_audio.wav"
        prepare_turn_audio(Path(row["duet_path"]), prepared_turn, destination, 16_000)
        item = {
            "version": VERSION, "pair_id": pair_id, "scope": "DEVELOPMENT_MODEL_VALIDATION_SET",
            "human_rating_read": False, "canonical_source": "RAW_COMPLETED_DUET",
            "raw_duet_sha256": sha256_file(Path(row["duet_path"])),
            "model_input_ref": str(destination.relative_to(output_root)).replace("\\", "/"),
            "model_input_sha256": sha256_file(destination), "turn": prepared_turn,
            "quality_gate": row.get("quality_gate"),
            "scorability_status": row.get("scorability_status"), "holdout": False,
        }
        _atomic_json(destination.parent / "input_provenance.json", item)
        items.append(item)
    summary = {"version": VERSION, "status": "MACHINE_INPUTS_READY_NO_VALIDATION_LABELS_READ",
               "items": items, "split_proof": split_proof, "holdout_processed": False}
    _atomic_json(output_root / "validation_inputs_summary.json", summary)
    return summary


def model_input_paths(root: Path, tournament_root: Path) -> dict[str, Path]:
    paths = {
        pair_id: root / "assessment_runs/T001_p22_calibrated_v01/pairs" / pair_id / "raw_learner_audio.wav"
        for pair_id in RATING_IDS
    }
    paths.update({
        pair_id: tournament_root / "validation_inputs" / pair_id / "raw_learner_audio.wav"
        for pair_id in VALIDATION_IDS
    })
    for pair_id, path in paths.items():
        if not path.is_file() or any(token in path.name.lower() for token in ("residual", "cancel")):
            raise ValueError(f"Missing/noncanonical P2.4 model input: {pair_id}")
    return paths


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_asr_tournament(root: Path, plan: dict, tournament_root: Path,
                       cache_root: Path) -> dict:
    """Run exact-revision CTranslate2 candidates on 6 references and all 17 inputs."""
    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download

    inputs = model_input_paths(root, tournament_root)
    human_root = root / "human_ground_truth/p22a_v1/asr_reference_v1"
    reference_ids = tuple(plan["evaluation"]["asr_reference_ids"])
    summaries = []
    for candidate in plan["candidates"]["asr"]:
        candidate_id = candidate["candidate_id"]
        output = tournament_root / "asr" / candidate_id
        output.mkdir(parents=True, exist_ok=True)
        print(f"[P2.4] ASR loading {candidate_id}", flush=True)
        try:
            local_model = snapshot_download(
                repo_id=candidate["model_id"], revision=candidate["revision"],
                cache_dir=cache_root / "huggingface", local_files_only=False,
            )
            with PeakMemoryMonitor() as load_memory:
                model = WhisperModel(local_model, device="cpu", compute_type="int8")
            records = []
            failures = []
            for index, pair_id in enumerate(ALL_P24_IDS, start=1):
                print(f"[P2.4] {candidate_id} {index}/{len(ALL_P24_IDS)} {pair_id}", flush=True)
                started = time.perf_counter()
                try:
                    with PeakMemoryMonitor() as monitor:
                        segments, info = model.transcribe(
                            str(inputs[pair_id]), language="en", beam_size=5,
                            word_timestamps=True, condition_on_previous_text=False,
                            vad_filter=False,
                        )
                        segment_rows = []
                        words = []
                        for segment in segments:
                            word_rows = []
                            for word in segment.words or []:
                                row = {"text": word.word.strip(), "start": float(word.start),
                                       "end": float(word.end), "probability": float(word.probability)}
                                word_rows.append(row); words.append(row)
                            segment_rows.append({"start": float(segment.start), "end": float(segment.end),
                                                 "text": segment.text, "avg_logprob": float(segment.avg_logprob),
                                                 "no_speech_prob": float(segment.no_speech_prob),
                                                 "words": word_rows})
                    runtime = time.perf_counter() - started
                    text = " ".join(segment["text"].strip() for segment in segment_rows).strip()
                    record = {
                        "version": VERSION, "pair_id": pair_id, "candidate_id": candidate_id,
                        "model_id": candidate["model_id"], "revision": candidate["revision"],
                        "audio_source": "RAW_COMPLETED_DUET_CROPPED_MASKED",
                        "input_sha256": sha256_file(inputs[pair_id]), "device": "cpu",
                        "dtype_quantization": "int8", "runtime_sec": runtime,
                        "peak_process_tree_ram_bytes": monitor.peak_rss,
                        "peak_vram_bytes": 0, "language_probability": float(info.language_probability),
                        "transcript": text, "normalized_transcript": normalize_transcript(text),
                        "segments": segment_rows, "words": words, "error": None,
                    }
                    _atomic_json(output / f"{pair_id}.json", record)
                    records.append(record)
                except Exception as exc:  # candidate failure must not break baseline
                    failures.append({"pair_id": pair_id, "error": f"{type(exc).__name__}: {exc}"})
            del model
            wer_rows = []
            for pair_id in reference_ids:
                record = next((row for row in records if row["pair_id"] == pair_id), None)
                if record is None:
                    continue
                reference = json.loads((human_root / pair_id / "reference.json").read_text(encoding="utf-8"))
                if reference.get("human_confirmed") is not True:
                    raise ValueError(f"Human ASR reference is not confirmed: {pair_id}")
                counts = word_error_counts(reference["human_verbatim_text"], record["transcript"])
                wer_rows.append({"pair_id": pair_id, **counts})
            totals = {name: sum(row[name] for row in wer_rows)
                      for name in ("substitutions", "insertions", "deletions", "reference_words")}
            micro_wer = ((totals["substitutions"] + totals["insertions"] + totals["deletions"])
                         / max(1, totals["reference_words"]))
            wers = [row["wer"] for row in wer_rows]
            summary = {
                "version": VERSION, "candidate_id": candidate_id, "model_id": candidate["model_id"],
                "revision": candidate["revision"], "status": "EVIDENCE_READY" if not failures else "PARTIAL_FAILURE",
                "package_versions": {"faster-whisper": _package_version("faster-whisper"),
                                     "ctranslate2": _package_version("ctranslate2")},
                "device": "cpu", "dtype_quantization": "int8",
                "micro_wer": micro_wer, "mean_wer": float(np.mean(wers)) if wers else None,
                "median_wer": float(np.median(wers)) if wers else None, **totals,
                "runtime_sec_reference_six": sum(row["runtime_sec"] for row in records
                                                  if row["pair_id"] in reference_ids),
                "runtime_sec_all_17": sum(row["runtime_sec"] for row in records),
                "peak_process_tree_ram_bytes": max(
                    [load_memory.peak_rss] + [row["peak_process_tree_ram_bytes"] for row in records]),
                "peak_vram_bytes": 0, "failure_count": len(failures), "failures": failures,
                "wer_items": wer_rows, "processed_ids": [row["pair_id"] for row in records],
                "holdout_processed": False,
            }
        except Exception as exc:
            summary = {"version": VERSION, "candidate_id": candidate_id,
                       "model_id": candidate["model_id"], "revision": candidate["revision"],
                       "status": "BACKEND_UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}",
                       "failure_count": len(ALL_P24_IDS), "processed_ids": [],
                       "holdout_processed": False}
        _atomic_json(output / "summary.json", summary)
        summaries.append(summary)
    result = {"version": VERSION, "status": "ASR_TOURNAMENT_COMPLETE",
              "candidates": summaries, "holdout_processed": False}
    _atomic_json(tournament_root / "asr_tournament_summary.json", result)
    return result


def normalized_edit_distance(left: str, right: str) -> float:
    a, b = words_for_wer(left), words_for_wer(right)
    previous = list(range(len(b) + 1))
    for i, word_a in enumerate(a, start=1):
        current = [i]
        for j, word_b in enumerate(b, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (word_a != word_b)))
        previous = current
    return previous[-1] / max(1, len(a), len(b))


def _coefficient_of_variation(values: list[float]) -> float:
    average = float(np.mean(values))
    return 0.0 if abs(average) < 1e-12 else float(np.std(values) / average)


def build_multi_asr_features(root: Path, plan: dict, tournament_root: Path) -> dict:
    target = json.loads((root / "task_profiles/T001_target_text_v1.json").read_text(encoding="utf-8"))
    target_text = target["confirmed_text"]
    candidate_ids = [item["candidate_id"] for item in plan["candidates"]["asr"]]
    rows = []
    for pair_id in ALL_P24_IDS:
        records = {}
        for candidate_id in candidate_ids:
            path = tournament_root / "asr" / candidate_id / f"{pair_id}.json"
            if path.is_file():
                records[candidate_id] = json.loads(path.read_text(encoding="utf-8"))
        if len(records) != len(candidate_ids):
            rows.append({"pair_id": pair_id, "status": "MISSING_ASR_CANDIDATE",
                         "available_candidates": sorted(records), "holdout": False})
            continue
        small = records["ASR_A_SMALL_EN"]
        distil = records["ASR_B_DISTIL_LARGE_V3"]
        turbo = records["ASR_C_LARGE_V3_TURBO"]
        small_record = {"original_asr": {"words": small["words"], "segments": small["segments"]}}
        small_features = transcript_features(small_record)
        coverages = [align_completeness(target_text, record["transcript"], candidate_id)["coverage"]
                     for candidate_id, record in records.items()]
        word_counts = [len(words_for_wer(record["transcript"])) for record in records.values()]
        features = {
            "small_mean_word_probability": small_features["mean_word_probability"],
            "small_low_confidence_word_fraction": small_features["low_confidence_word_fraction"],
            "small_vs_distil_normalized_edit_distance": normalized_edit_distance(
                small["transcript"], distil["transcript"]),
            "small_vs_turbo_normalized_edit_distance": normalized_edit_distance(
                small["transcript"], turbo["transcript"]),
            "three_asr_word_count_coefficient_of_variation": _coefficient_of_variation(word_counts),
            "target_alignment_coverage_range": max(coverages) - min(coverages),
        }
        rows.append({"pair_id": pair_id, "status": "MULTI_ASR_STABILITY_READY",
                     "features": features, "transcript_refs": {
                         candidate_id: f"asr/{candidate_id}/{pair_id}.json" for candidate_id in records
                     }, "asr_disagreement_is_pronunciation_error": False, "holdout": False})
    result = {"version": VERSION, "status": "MULTI_ASR_STABILITY_COMPLETE",
              "items": rows, "holdout_processed": False}
    _atomic_json(tournament_root / "multi_asr_stability_v1.json", result)
    return result


def run_whisperx_alignment(root: Path, plan: dict, tournament_root: Path,
                           python_executable: Path) -> dict:
    """Run isolated alignment against canonical small.en text without overwriting it."""
    inputs = model_input_paths(root, tournament_root)
    small_root = tournament_root / "asr/ASR_A_SMALL_EN"
    request_items = []
    for pair_id in ALL_P24_IDS:
        record = json.loads((small_root / f"{pair_id}.json").read_text(encoding="utf-8"))
        request_items.append({
            "pair_id": pair_id, "audio_path": str(inputs[pair_id]),
            "input_sha256": sha256_file(inputs[pair_id]),
            "segments": [{"start": segment["start"], "end": segment["end"],
                          "text": segment["text"]} for segment in record["segments"]],
        })
    candidate = next(item for item in plan["candidates"]["alignment"]
                     if item["candidate_id"] == "ALIGN_WHISPERX_WAV2VEC2")
    request = {"version": VERSION, "align_model": candidate["align_model"],
               "model_dir": str(tournament_root / "whisperx_model_cache"),
               "items": request_items, "holdout_processed": False}
    request_path = tournament_root / "whisperx_alignment_request.json"
    output_path = tournament_root / "whisperx_alignment_summary.json"
    _atomic_json(request_path, request)
    command = [str(python_executable), str(root / "scripts/p24_whisperx_worker.py"),
               "--request", str(request_path), "--output", str(output_path)]
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=root, check=False)
    if proc.returncode or not output_path.is_file():
        result = {"version": VERSION, "status": "BACKEND_UNAVAILABLE",
                  "candidate_id": "ALIGN_WHISPERX_WAV2VEC2",
                  "returncode": proc.returncode, "runtime_sec": time.perf_counter() - started,
                  "canonical_evidence_overwritten": False, "holdout_processed": False}
        _atomic_json(output_path, result)
        return result
    result = json.loads(output_path.read_text(encoding="utf-8"))
    result["subprocess_runtime_sec"] = time.perf_counter() - started
    _atomic_json(output_path, result)
    return result


def build_whisperx_fluency(root: Path, tournament_root: Path) -> dict:
    from speaking_evidence.fluency import measure_fluency

    alignment_path = tournament_root / "whisperx_alignment_summary.json"
    alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
    if alignment.get("status") == "BACKEND_UNAVAILABLE":
        return {"version": VERSION, "status": "BACKEND_UNAVAILABLE", "items": [],
                "canonical_evidence_overwritten": False, "holdout_processed": False}
    inputs = model_input_paths(root, tournament_root)
    items = []
    for aligned in alignment["items"]:
        pair_id = aligned["pair_id"]
        if aligned["status"] != "ALIGNMENT_READY":
            items.append({"pair_id": pair_id, "status": "ALIGNMENT_FAILED", "features": None})
            continue
        if pair_id in RATING_IDS:
            provenance = json.loads((root / "assessment_runs/T001_p22_calibrated_v01/pairs" /
                                     pair_id / "raw_evidence.json").read_text(encoding="utf-8"))
        else:
            provenance = json.loads((tournament_root / "validation_inputs" / pair_id /
                                     "input_provenance.json").read_text(encoding="utf-8"))
        turn = provenance["turn"]
        origin = float(turn["start_sec"])
        local_turn = {"start_sec": 0.0, "end_sec": float(turn["end_sec"] - origin),
                      "learner_intervals": [
                          {"start": float(item["start"] - origin),
                           "end": float(item["end"] - origin)}
                          for item in turn["learner_intervals"]
                      ]}
        words = [{"text": word["text"], "start_sec": float(word["start"]),
                  "end_sec": float(word["end"]), "probability": word.get("score")}
                 for word in aligned["words"]
                 if word.get("start") is not None and word.get("end") is not None]
        features = measure_fluency(local_turn, words, 0.25, 0.70)
        baseline = json.loads((tournament_root / "asr/ASR_A_SMALL_EN" /
                               f"{pair_id}.json").read_text(encoding="utf-8"))
        baseline_words = baseline["words"]
        comparable = min(len(words), len(baseline_words))
        start_deltas = [abs(words[index]["start_sec"] - baseline_words[index]["start"])
                        for index in range(comparable)]
        end_deltas = [abs(words[index]["end_sec"] - baseline_words[index]["end"])
                      for index in range(comparable)]
        items.append({
            "pair_id": pair_id, "status": "WHISPERX_FLUENCY_READY", "features": features,
            "timing_comparison": {
                "comparable_word_count_by_position": comparable,
                "mean_absolute_start_delta_sec": float(np.mean(start_deltas)) if start_deltas else None,
                "mean_absolute_end_delta_sec": float(np.mean(end_deltas)) if end_deltas else None,
                "whisperx_aligned_word_count": len(words),
                "canonical_word_count": len(baseline_words),
                "unalignable_word_count": aligned["unalignable_word_count"],
            },
            "canonical_evidence_overwritten": False, "input_sha256": sha256_file(inputs[pair_id]),
        })
    result = {"version": VERSION, "status": "WHISPERX_FLUENCY_EVIDENCE_COMPLETE",
              "items": items, "canonical_evidence_overwritten": False,
              "holdout_processed": False}
    _atomic_json(tournament_root / "whisperx_fluency_evidence_v1.json", result)
    return result


def run_apa_candidates(root: Path, plan: dict, tournament_root: Path) -> dict:
    inputs = model_input_paths(root, tournament_root)
    request_items = [{"pair_id": pair_id, "audio_path": str(path),
                      "input_sha256": sha256_file(path)} for pair_id, path in inputs.items()]
    architecture = {
        "APA_1_WAV2VEC2_LARGE_GENERAL": ("wav2vec2", "facebook/wav2vec2-large"),
        "APA_2F_HUBERT_BASE_LS960_GENERAL": ("hubert", "facebook/hubert-base-ls960"),
    }
    summaries = []
    for candidate in plan["candidates"]["apa"]:
        candidate_id = candidate["candidate_id"]
        output_path = tournament_root / "apa" / f"{candidate_id}_summary.json"
        if candidate["weight_bytes"] > plan["resource_limits"]["maximum_apa_weight_file_bytes"]:
            summary = {"version": VERSION, "candidate": candidate,
                       "status": "BACKEND_UNAVAILABLE", "reason": "FROZEN_RESOURCE_GATE",
                       "direct_pretrained_scores_emitted": False, "items": [],
                       "holdout_processed": False}
            _atomic_json(output_path, summary); summaries.append(summary); continue
        model_architecture, base_model = architecture[candidate_id]
        request_candidate = {**candidate, "architecture": model_architecture,
                             "base_model": base_model,
                             "revision": candidate["repository_revision"]}
        request = {"version": VERSION, "candidate": request_candidate,
                   "items": request_items, "holdout_processed": False}
        request_path = tournament_root / "apa" / f"{candidate_id}_request.json"
        _atomic_json(request_path, request)
        command = [os.sys.executable, str(root / "scripts/p24_apa_worker.py"),
                   "--request", str(request_path), "--output", str(output_path)]
        print(f"[P2.4] APA worker {candidate_id}", flush=True)
        proc = subprocess.run(command, cwd=root, check=False)
        if proc.returncode or not output_path.is_file():
            summary = {"version": VERSION, "candidate": request_candidate,
                       "status": "BACKEND_UNAVAILABLE", "returncode": proc.returncode,
                       "direct_pretrained_scores_emitted": False, "items": [],
                       "holdout_processed": False}
            _atomic_json(output_path, summary)
        else:
            summary = json.loads(output_path.read_text(encoding="utf-8"))
        summaries.append(summary)
    result = {"version": VERSION, "status": "APA_CANDIDATE_RUN_COMPLETE",
              "candidates": summaries, "holdout_processed": False}
    _atomic_json(tournament_root / "apa_tournament_summary.json", result)
    return result


def build_apa_pca_features(plan: dict, tournament_root: Path) -> dict:
    items = []
    for candidate in plan["candidates"]["apa"]:
        candidate_id = candidate["candidate_id"]
        if candidate_id == "APA_2_HUBERT_XLARGE_LS960_FT_CTC":
            continue
        summary_path = tournament_root / "apa" / f"{candidate_id}_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        ready = [item for item in summary.get("items", [])
                 if item.get("status") == "PRETRAINED_EMBEDDING_FEATURE_READY"]
        if len(ready) != len(ALL_P24_IDS):
            items.append({"candidate_id": candidate_id, "status": "BACKEND_UNAVAILABLE",
                          "available_embeddings": len(ready), "features": []})
            continue
        embeddings = {}
        for item in ready:
            embeddings[item["pair_id"]] = np.load(item["embedding_ref"])["mean_pooled_embedding"]
        train = np.stack([embeddings[pair_id] for pair_id in RATING_IDS])
        mean, vectors, singular = fit_pca(train, components=2)
        all_matrix = np.stack([embeddings[pair_id] for pair_id in ALL_P24_IDS])
        projected = apply_pca(all_matrix, mean, vectors)
        feature_rows = [{"pair_id": pair_id, "pca_component_1": float(projected[index, 0]),
                         "pca_component_2": float(projected[index, 1])}
                        for index, pair_id in enumerate(ALL_P24_IDS)]
        pca_path = tournament_root / "apa" / f"{candidate_id}_pca_v1.npz"
        np.savez_compressed(pca_path, mean=mean, components=vectors, singular_values=singular)
        items.append({"candidate_id": candidate_id, "status": "PRETRAINED_EMBEDDING_FEATURE_READY",
                      "output_type": "PRETRAINED_EMBEDDING_FEATURE",
                      "direct_pretrained_score": None,
                      "pca_fit_ids": list(RATING_IDS), "pca_fit_used_human_labels": False,
                      "pca_ref": str(pca_path).replace("\\", "/"), "features": feature_rows})
    result = {"version": VERSION, "status": "APA_PCA_FEATURES_COMPLETE", "items": items,
              "embeddings_mislabeled_as_direct_scores": False, "holdout_processed": False}
    _atomic_json(tournament_root / "apa_pca_features_v1.json", result)
    return result


def _attach_mapping_diagnostics(mapping: dict, runtime_sec: float | None,
                                missing_rate: float = 0.0) -> dict:
    result = dict(mapping)
    predictions = result.get("loo_predictions")
    if predictions:
        result["prediction_variance"] = float(np.var(predictions))
    result["feature_runtime_sec"] = runtime_sec
    result["missing_evidence_rate"] = missing_rate
    result["coefficient_stability"] = (
        "FULL_LOOCV_PREDICTION_STABILITY_REPORTED; coefficient-sign resampling omitted because N=12"
    )
    return result


def _asr_selection(plan: dict, asr_summary: dict) -> dict:
    by_id = {item["candidate_id"]: item for item in asr_summary["candidates"]}
    baseline_id = "ASR_A_SMALL_EN"
    baseline = by_id[baseline_id]
    selected = baseline_id
    reason = "BASELINE_RETAINED_BY_FROZEN_RULE"
    for candidate_id in ("ASR_B_DISTIL_LARGE_V3", "ASR_C_LARGE_V3_TURBO"):
        candidate = by_id[candidate_id]
        if candidate.get("status") != "EVIDENCE_READY" or candidate.get("failure_count"):
            continue
        absolute = baseline["micro_wer"] - candidate["micro_wer"]
        relative = absolute / max(baseline["micro_wer"], 1e-12)
        resource_ok = (candidate["runtime_sec_reference_six"]
                       <= 4 * baseline["runtime_sec_reference_six"]
                       and candidate["peak_process_tree_ram_bytes"]
                       <= 4 * baseline["peak_process_tree_ram_bytes"])
        if resource_ok and (absolute >= 0.01 or relative >= 0.15):
            selected, baseline = candidate_id, candidate
            reason = "FROZEN_ASR_IMPROVEMENT_RULE_MET"
    return {"selected": selected, "status": ("BASELINE_RETAINED" if selected == baseline_id
                                               else "SELECTED_PRELIMINARY"),
            "reason": reason}


def _feature_maps(tournament_root: Path) -> tuple[dict, dict, dict]:
    multi = json.loads((tournament_root / "multi_asr_stability_v1.json").read_text(encoding="utf-8"))
    multi_map = {item["pair_id"]: item.get("features") for item in multi["items"]
                 if item.get("features")}
    aligned_path = tournament_root / "whisperx_fluency_evidence_v1.json"
    aligned = json.loads(aligned_path.read_text(encoding="utf-8"))
    aligned_map = {item["pair_id"]: item.get("features") for item in aligned.get("items", [])
                   if item.get("features")}
    apa = json.loads((tournament_root / "apa_pca_features_v1.json").read_text(encoding="utf-8"))
    apa_maps = {}
    for candidate in apa["items"]:
        if candidate.get("status") == "PRETRAINED_EMBEDDING_FEATURE_READY":
            apa_maps[candidate["candidate_id"]] = {
                item["pair_id"]: item for item in candidate["features"]
            }
    return multi_map, aligned_map, apa_maps


def _build_calibration_rows(root: Path, tournament_root: Path) -> list[dict]:
    ratings = json.loads((root / "human_ground_truth/p22a_v1/ratings_v2.json").read_text(
        encoding="utf-8"))["items"]
    multi_map, aligned_map, apa_maps = _feature_maps(tournament_root)
    target = json.loads((root / "task_profiles/T001_target_text_v1.json").read_text(
        encoding="utf-8"))["confirmed_text"]
    rows = []
    for rating in ratings:
        pair_id = rating["pair_id"]
        evidence = json.loads((root / "assessment_runs/T001_p22_calibrated_v01/pairs" /
                               pair_id / "evidence.json").read_text(encoding="utf-8"))
        baseline_pron = json.loads((root / "assessment_runs/T001_p22_calibrated_v01/pairs" /
                                    pair_id / "pronunciation_asr_baseline_v1.json").read_text(
                                        encoding="utf-8"))
        fluency = evidence["aggregate_fluency_evidence"]
        acoustic = evidence["turns"][0]["acoustic"]
        transcript = evidence["turns"][0]["transcript"]
        recognition = transcript_features({"original_asr": transcript})
        pron_proxy = baseline_pron["utterance"]["recognition_proxy"]
        row = {**rating, **fluency, **acoustic, **recognition,
               "pron_mean_word_probability": pron_proxy["mean_word_probability"],
               "pron_low_confidence_word_fraction": pron_proxy["low_confidence_word_fraction"],
               "pron_target_asr_match_coverage": pron_proxy["target_asr_match_coverage"]}
        if pair_id in aligned_map:
            row.update({f"wx_{name}": value for name, value in aligned_map[pair_id].items()
                        if isinstance(value, (int, float))})
        if pair_id in multi_map:
            row.update(multi_map[pair_id])
        for candidate_id, prefix in (("APA_1_WAV2VEC2_LARGE_GENERAL", "apa1"),
                                     ("APA_2F_HUBERT_BASE_LS960_GENERAL", "apa2f")):
            if candidate_id in apa_maps and pair_id in apa_maps[candidate_id]:
                row[f"{prefix}_pca_component_1"] = apa_maps[candidate_id][pair_id]["pca_component_1"]
                row[f"{prefix}_pca_component_2"] = apa_maps[candidate_id][pair_id]["pca_component_2"]
        rows.append(row)
    return rows


def build_completeness_by_asr(root: Path, plan: dict, tournament_root: Path) -> dict:
    from speaking_evidence.pronunciation import align_target_for_pronunciation

    target = json.loads((root / "task_profiles/T001_target_text_v1.json").read_text(
        encoding="utf-8"))["confirmed_text"]
    backends = []
    for candidate in plan["candidates"]["asr"]:
        candidate_id = candidate["candidate_id"]
        items = []
        for pair_id in RATING_IDS:
            record = json.loads((tournament_root / "asr" / candidate_id /
                                 f"{pair_id}.json").read_text(encoding="utf-8"))
            completeness = align_completeness(target, record["transcript"], candidate_id)
            alignment = align_target_for_pronunciation(target, record["words"])
            uncertain = sum(item["status"] == "SUBSTITUTED_OR_UNCERTAIN"
                            for item in alignment["target_words"])
            items.append({"pair_id": pair_id, "coverage": completeness["coverage"],
                          "matched": len(completeness["matched_sequence"]),
                          "omissions": len(completeness["omissions"]),
                          "insertions": len(completeness["insertions"]),
                          "substitutions_or_uncertain": uncertain})
        backends.append({
            "candidate_id": candidate_id,
            "mean_coverage": float(np.mean([item["coverage"] for item in items])),
            "total_matched": sum(item["matched"] for item in items),
            "total_omissions": sum(item["omissions"] for item in items),
            "total_insertions": sum(item["insertions"] for item in items),
            "total_substitutions_or_uncertain": sum(item["substitutions_or_uncertain"] for item in items),
            "items": items,
        })
    result = {"version": VERSION, "criterion": "ASR-assisted Reading Completeness",
              "status": "EVIDENCE_ONLY", "backends": backends,
              "warning": "ASR differences are not proven learner errors.",
              "holdout_processed": False}
    _atomic_json(tournament_root / "completeness_by_asr_v1.json", result)
    return result


def run_criterion_tournament(root: Path, plan: dict, plan_digest: str,
                             tournament_root: Path) -> dict:
    rows = _build_calibration_rows(root, tournament_root)
    wx_features = tuple(f"wx_{name}" for name in FLUENCY_FEATURES)
    mappings: dict[str, dict[str, dict]] = {"fluency": {}, "pronunciation": {},
                                           "intelligibility": {}, "prosody": {}}
    mappings["fluency"]["F0_BASELINE"] = _attach_mapping_diagnostics(
        fit_support_aware_mapping(rows, "fluency", FLUENCY_FEATURES), 0.0)
    if all(all(name in row for name in wx_features) for row in rows):
        mappings["fluency"]["F1_WHISPERX"] = _attach_mapping_diagnostics(
            fit_support_aware_mapping(rows, "fluency", wx_features), None)
    else:
        mappings["fluency"]["F1_WHISPERX"] = {"status": "BACKEND_UNAVAILABLE"}
    for candidate_id, features in (
        ("F2_APA1", ("apa1_pca_component_1", "apa1_pca_component_2")),
        ("F2_APA2F", ("apa2f_pca_component_1", "apa2f_pca_component_2")),
        ("F3_HYBRID", ("pause_ratio", "mean_length_of_run_words", "apa1_pca_component_1")),
    ):
        mappings["fluency"][candidate_id] = (_attach_mapping_diagnostics(
            fit_support_aware_mapping(rows, "fluency", features), None)
            if all(all(name in row for name in features) for row in rows)
            else {"status": "BACKEND_UNAVAILABLE"})

    pronunciation_candidates = {
        "P0_ASR_RECOGNITION": ("pron_mean_word_probability",
                               "pron_low_confidence_word_fraction",
                               "pron_target_asr_match_coverage"),
        "P1_APA1": ("apa1_pca_component_1", "apa1_pca_component_2"),
        "P2_APA2F": ("apa2f_pca_component_1", "apa2f_pca_component_2"),
    }
    for candidate_id, features in pronunciation_candidates.items():
        mappings["pronunciation"][candidate_id] = (_attach_mapping_diagnostics(
            enrich_binary_mapping(rows, "pronunciation", features), None)
            if all(all(name in row for name in features) for row in rows)
            else {"status": "BACKEND_UNAVAILABLE"})

    mappings["intelligibility"]["I0_SINGLE_ASR"] = _attach_mapping_diagnostics(
        enrich_binary_mapping(rows, "intelligibility", INTELLIGIBILITY_FEATURES), 0.0)
    multi_features = tuple(plan["fixed_feature_sets"]["intelligibility_multi_asr"])
    hybrid_features = tuple(plan["fixed_feature_sets"]["intelligibility_hybrid"])
    mappings["intelligibility"]["I1_MULTI_ASR"] = _attach_mapping_diagnostics(
        enrich_binary_mapping(rows, "intelligibility", multi_features, class_weighted=True), None)
    mappings["intelligibility"]["I2_MULTI_ASR_MINIMAL"] = _attach_mapping_diagnostics(
        enrich_binary_mapping(rows, "intelligibility", hybrid_features, class_weighted=True), None)

    mappings["prosody"]["R0_PRAAT"] = _attach_mapping_diagnostics(
        fit_support_aware_mapping(rows, "prosody", PROSODY_FEATURES), 0.0)
    for candidate_id, features in (
        ("R1_APA1", ("apa1_pca_component_1", "apa1_pca_component_2")),
        ("R1_APA2F", ("apa2f_pca_component_1", "apa2f_pca_component_2")),
        ("R2_HYBRID", ("f0_range_semitones", "intensity_std_db", "apa1_pca_component_1")),
    ):
        mappings["prosody"][candidate_id] = (_attach_mapping_diagnostics(
            fit_support_aware_mapping(rows, "prosody", features), None)
            if all(all(name in row for name in features) for row in rows)
            else {"status": "BACKEND_UNAVAILABLE"})

    selections = {
        "fluency": select_binary_candidate(plan, "F0_BASELINE", mappings["fluency"]),
        "pronunciation": select_binary_candidate(plan, "P0_ASR_RECOGNITION",
                                                   mappings["pronunciation"]),
        "intelligibility": select_binary_candidate(plan, "I0_SINGLE_ASR",
                                                     mappings["intelligibility"], True),
        "prosody": select_multilevel_candidate(plan, "R0_PRAAT", mappings["prosody"]),
        "completeness": {"selected": "DETERMINISTIC_ASR_ASSISTED",
                         "status": "BASELINE_RETAINED",
                         "reason": "Neural scorer prohibited by frozen plan"},
    }
    for criterion in ("fluency", "pronunciation", "intelligibility", "prosody"):
        selected_mapping = mappings[criterion][selections[criterion]["selected"]]
        if selected_mapping.get("status") == "MACHINE_CALIBRATION_UNSTABLE":
            selections[criterion]["status"] = "MACHINE_CALIBRATION_UNSTABLE"
    result = {"version": VERSION, "status": "CRITERION_TOURNAMENT_COMPLETE",
              "plan_sha256": plan_digest, "n": len(rows), "mappings": mappings,
              "selections": selections, "validation_human_ratings_read": False,
              "overall_score_created": False, "holdout_processed": False,
              "labels": ["DEVELOPMENT / PRELIMINARY", "NOT CEFR", "NOT B2", "NOT IELTS"]}
    _atomic_json(tournament_root / "criterion_tournament_summary.json", result)
    write_winner_freeze(tournament_root / "winner_freeze_v1.json", plan_digest, selections)
    return result


def fit_pca(train_embeddings: np.ndarray, components: int = 2) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = train_embeddings.mean(axis=0)
    centered = train_embeddings - mean
    _, singular_values, right = np.linalg.svd(centered, full_matrices=False)
    vectors = right[:components]
    return mean, vectors, singular_values[:components]


def apply_pca(embeddings: np.ndarray, mean: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    return (embeddings - mean) @ vectors.T


def enrich_binary_mapping(rows: list[dict], label: str, features: tuple[str, ...],
                          class_weighted: bool = False) -> dict:
    mapping = fit_restricted_binary_mapping(rows, label, features,
                                            class_weighted=class_weighted)
    predicted = mapping.get("predicted_vs_human", [])
    if predicted:
        human = np.asarray([row["human"] for row in predicted], dtype=float)
        expected = np.asarray([row["predicted_expected_score"] for row in predicted], dtype=float)
        mapping["prediction_variance"] = float(np.var(expected))
        mapping["majority_baseline_accuracy"] = max(Counter(human).values()) / len(human)
        mapping["majority_baseline_balanced_accuracy"] = 0.5
    return mapping


def select_binary_candidate(plan: dict, baseline_id: str, mappings: dict[str, dict],
                            intelligibility: bool = False) -> dict:
    baseline = mappings[baseline_id]
    selected = baseline_id
    reason = "BASELINE_RETAINED_BY_DEFAULT"
    for candidate_id in sorted(mappings):
        if candidate_id == baseline_id:
            continue
        candidate = mappings[candidate_id]
        if candidate.get("status") != "DEVELOPMENT_PRELIMINARY_RANGE_LIMITED":
            continue
        if intelligibility and (candidate.get("majority_class_collapse")
                                or candidate.get("balanced_accuracy", 0) < 0.60):
            continue
        mae_gain = baseline.get("loo_mae", math.inf) - candidate.get("loo_mae", math.inf)
        balanced_gain = (candidate.get("balanced_accuracy", 0)
                         - baseline.get("balanced_accuracy", 0))
        mae_not_worse = candidate.get("loo_mae", math.inf) <= baseline.get("loo_mae", math.inf) + 0.05
        if mae_gain >= 0.05 or (balanced_gain >= 0.10 and mae_not_worse):
            selected, baseline = candidate_id, candidate
            reason = "FROZEN_BINARY_PROMOTION_RULE_MET"
    return {"selected": selected, "reason": reason,
            "status": ("BASELINE_RETAINED" if selected == baseline_id else "SELECTED_PRELIMINARY")}


def select_multilevel_candidate(plan: dict, baseline_id: str,
                                mappings: dict[str, dict]) -> dict:
    baseline = mappings[baseline_id]
    selected = baseline_id
    reason = "BASELINE_RETAINED_BY_DEFAULT"
    for candidate_id in sorted(mappings):
        if candidate_id == baseline_id:
            continue
        candidate = mappings[candidate_id]
        if candidate.get("status") != "DEVELOPMENT_PRELIMINARY_MULTI_LEVEL":
            continue
        mae_gain = baseline.get("loo_mae", math.inf) - candidate.get("loo_mae", math.inf)
        correlation_gain = ((candidate.get("spearman_correlation") or -1)
                            - (baseline.get("spearman_correlation") or -1))
        mae_not_worse = candidate.get("loo_mae", math.inf) <= baseline.get("loo_mae", math.inf) + 0.05
        if mae_gain >= 0.05 or (correlation_gain >= 0.10 and mae_not_worse):
            selected, baseline = candidate_id, candidate
            reason = "FROZEN_MULTI_LEVEL_PROMOTION_RULE_MET"
    return {"selected": selected, "reason": reason,
            "status": ("BASELINE_RETAINED" if selected == baseline_id else "SELECTED_PRELIMINARY")}


def write_winner_freeze(path: Path, plan_digest: str, selections: dict,
                        validation_ids: tuple[str, ...] = VALIDATION_IDS) -> dict:
    result = {"version": VERSION, "status": "MODEL_SELECTION_FROZEN_BEFORE_VALIDATION_RATINGS",
              "plan_sha256": plan_digest, "criterion_selections": selections,
              "development_validation_ids": list(validation_ids),
              "validation_human_ratings_read": False, "validation_runs_allowed": 1,
              "holdout_processed": False, "overall_score_created": False}
    _atomic_json(path, result)
    return result
