"""Frozen, offline-first competition demo services.

This module never reads teacher ratings and never fits a model. It validates a
machine-only cache for known demonstrations and can run the already-frozen
pipeline for a new completed Duet.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

from duet_segmenter.pipeline import load_config
from duet_segmenter.profile import build_template_profile
from duet_segmenter.smart_pipeline import run_profiled
from speaking_evidence.asr import FasterWhisperBackend
from speaking_evidence.audio import prepare_turn_audio
from speaking_evidence.fluency import measure_fluency
from speaking_evidence.p22 import align_completeness, apply_mapping
from speaking_evidence.p24d_multipa import (
    aggregate_video,
    apply_fitted_mapping,
    segment_closed_response,
    sha256_file,
    write_wav_slice,
)


CACHE_VERSION = "competition-demo-cache-v2"
CACHE_NAME = "competition_demo_cache_v2.json"
TARGET_PROFILE_NAME = "competition_target_profile_v2.json"
TARGET_PROFILE_SHA256 = "e2a4b2f1ee77860bab9a1a075d07bf61a27fe9ab641a71719dc129def1fb9da2"
DEMO_IDS = ("T001-D043", "T001-D064", "T001-D048")
DEMO_LABELS = {
    "T001-D064": "Demo Student A",
    "T001-D043": "Demo Student B",
    "T001-D048": "Demo Student C",
}
DEMO_ROLES = {
    "T001-D043": "Main demo",
    "T001-D064": "Consistency example",
    "T001-D048": "Challenge case",
}
FROZEN_FILES = {
    "p24d_plan_sha256": ("p24d_multipa_plan_v1.json",
                         "90755aaa169b605c7b9a070ae411dc28366a2b3e568e4daf2e81dc15a4cee1c1"),
    "p24d_report_sha256": ("MULTIPA_COMPETITION_SCORER_REPORT.md",
                           "b7824a624a8197db59f297e9f328bb0fdcb2d3400c4e4ae323bf6838786deecb"),
    "p25_plan_sha256": ("p25_frozen_mini_validation_plan_v1.json",
                        "e75710e13781e154adeacd9683d6afde8a992220fb3c85adcc48e7ffac1c0d54"),
    "target_sha256": ("task_profiles/T001_target_text_v1.json",
                      "a58cbaf8949d47fb1257b828b5dfcb441520b53f414c27cc57ea850bc79924c2"),
    "split_sha256": ("cohort_runs/T001_p14/data_split_v2.json",
                     "cca57f3e7d5ae3918e474f6bf2be05a76b353281633ea190976aeb03911d461b"),
}
CHECKPOINT_SHA256 = "cc1f02622c763e82f29d7d4d5a073ed45bf9d829013e2c6cc726371fe2d024e8"
MULTIPA_COMMIT = "a8d83ec1d80f9db60e6d32227cb1c562ee5e6022"


class StaleDemoCacheError(ValueError):
    """Raised when cached machine evidence no longer matches frozen inputs."""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_default(value: object) -> object:
    """Convert numeric scalar outputs without changing their measured value."""
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_frozen_scorer(root: Path) -> dict[str, str]:
    """Verify immutable scorer/config hashes without opening human data."""
    verified = {}
    for key, (relative, expected) in FROZEN_FILES.items():
        path = root / relative
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"Frozen scorer/config changed: {relative}")
        verified[key] = actual
    plan = _load(root / "p25_frozen_mini_validation_plan_v1.json")
    if (plan.get("training_or_refitting_allowed") is not False
            or plan.get("threshold_or_feature_change_allowed") is not False
            or plan.get("model_reselection_allowed") is not False
            or plan.get("holdout_processed") is not False
            or plan["criteria"]["intelligibility"].get("machine_score") is not None
            or plan["criteria"].get("overall") is not None):
        raise ValueError("Frozen scorer safety policy changed")
    return verified


def load_competition_target(root: Path) -> dict:
    """Load the audited competition target boundary without changing v1 history."""
    path = root / TARGET_PROFILE_NAME
    if sha256_file(path) != TARGET_PROFILE_SHA256:
        raise ValueError("Competition target profile changed")
    target = _load(path)
    if (target.get("version") != "competition-target-v2"
            or target.get("classification") != "TITLE_TOPIC_LABEL"
            or target.get("scoring_action") != "EXCLUDE_TOPIC_FROM_READING_COMPLETENESS"
            or not target.get("scored_passage")):
        raise ValueError("Competition target audit policy changed")
    return target


def _manifest_rows(root: Path) -> dict[str, dict]:
    rows = _load(root / "cohort_runs/T001_p14/development_manifest_v3.json")
    return {row["pair_id"]: row for row in rows}


def resolve_demo_video(root: Path, pair_id: str, expected_sha256: str) -> Path:
    if pair_id not in DEMO_IDS:
        raise ValueError("Unknown competition demonstration")
    row = _manifest_rows(root).get(pair_id)
    if not row:
        raise FileNotFoundError(f"Development source is unavailable for {pair_id}")
    path = Path(row["duet_path"])
    if not path.is_file() or sha256_file(path) != expected_sha256:
        raise StaleDemoCacheError(f"Source video changed or is unavailable for {pair_id}")
    return path


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_all_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_all_keys(item))
    return keys


def _evidence_ref_exists(item: dict, reference: str) -> bool:
    value: object = item
    for part in reference.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return False
    return True


def validate_deterministic_feedback(item: dict) -> None:
    feedback = item.get("feedback", {})
    if (feedback.get("engine") != "DETERMINISTIC_MEASURED_EVIDENCE_V1"
            or feedback.get("llm_used") is not False
            or feedback.get("grammar_or_vocabulary_comment") is not False
            or feedback.get("accent_shaming") is not False):
        raise ValueError("Feedback safety policy failed")
    for name in ("strength", "focus_next", "try_this"):
        block = feedback.get(name, {})
        if not isinstance(block.get("text"), str) or not block["text"].strip():
            raise ValueError(f"Feedback block is empty: {name}")
        if any(not _evidence_ref_exists(item, ref) for ref in block.get("evidence_refs", [])):
            raise ValueError(f"Feedback block cites missing evidence: {name}")


def validate_demo_cache(root: Path, cache: dict, verify_media: bool = True) -> dict:
    """Reject stale, leaky, holdout, incomplete, or fabricated demo caches."""
    frozen = verify_frozen_scorer(root)
    if cache.get("version") != CACHE_VERSION:
        raise StaleDemoCacheError("Unexpected demo cache version")
    if tuple(cache.get("demo_ids", [])) != DEMO_IDS:
        raise StaleDemoCacheError("Demo cache membership changed")
    if cache.get("frozen_hashes") != frozen:
        raise StaleDemoCacheError("Demo cache scorer hashes are stale")
    if cache.get("target_profile_sha256") != TARGET_PROFILE_SHA256:
        raise StaleDemoCacheError("Demo cache target profile is stale")
    load_competition_target(root)
    if (cache.get("holdout_processed") is not False
            or cache.get("refit_performed") is not False
            or cache.get("machine_intelligibility") is not None
            or cache.get("overall_score") is not None):
        raise StaleDemoCacheError("Demo cache safety policy failed")
    forbidden = [key for key in _all_keys(cache)
                 if any(token in key for token in ("teacher", "human_rating", "validation_rating"))]
    if forbidden:
        raise StaleDemoCacheError("Private rating fields are prohibited in the demo cache")
    items = cache.get("items", [])
    if tuple(item.get("pair_id") for item in items) != DEMO_IDS:
        raise StaleDemoCacheError("Demo cache item order changed")
    for item in items:
        if (item.get("genuine_frozen_inference") is not True
                or item.get("fake_or_placeholder_score") is not False
                or item.get("holdout") is not False
                or item.get("scorability_status") != "SCORABLE_CLEAN"
                or item.get("audio_source_type") != "RAW_CROPPED"):
            raise StaleDemoCacheError(f"Unsafe demo item: {item.get('pair_id')}")
        if (item.get("target_profile_sha256") != TARGET_PROFILE_SHA256
                or item.get("target_topic") != "One memorable event"):
            raise StaleDemoCacheError(f"Stale target evidence: {item.get('pair_id')}")
        scores = item.get("scores", {})
        if (set(scores) != {"pronunciation", "fluency", "prosody", "completeness"}
                or any(not isinstance(scores[name], (int, float)) for name in scores)):
            raise StaleDemoCacheError(f"Invalid genuine scores: {item.get('pair_id')}")
        if verify_media:
            model_input = root / "assessment_runs/T001_p24_tournament_v1" / item["model_input_ref"]
            if not model_input.is_file() or sha256_file(model_input) != item["model_input_sha256"]:
                raise StaleDemoCacheError(f"RAW_CROPPED input is stale: {item['pair_id']}")
            resolve_demo_video(root, item["pair_id"], item["raw_duet_sha256"])
        validate_deterministic_feedback(item)
    return cache


def load_demo_cache(root: Path, pair_id: str, verify_media: bool = True) -> dict:
    cache = validate_demo_cache(root, _load(root / CACHE_NAME), verify_media=verify_media)
    try:
        return next(item for item in cache["items"] if item["pair_id"] == pair_id)
    except StopIteration as exc:
        raise KeyError(pair_id) from exc


def _word_evidence(chunks: list[dict], limit: int = 3) -> list[dict]:
    """Select low relative model evidence as review prompts, never error labels."""
    ignored = {"a", "an", "and", "at", "for", "in", "it", "my", "of", "on", "one",
               "the", "there", "to", "was", "were"}
    candidates: dict[str, dict] = {}
    for chunk in chunks:
        words = chunk.get("word_text", [])
        accuracy = chunk.get("word_accuracy", [])
        stress = chunk.get("word_stress", [])
        if len(words) != len(accuracy):
            continue
        for index, word in enumerate(words):
            normalized = str(word).strip().lower()
            if len(normalized) < 3 or normalized in ignored:
                continue
            row = {
                "word": normalized,
                "accuracy_evidence": round(float(accuracy[index]), 4),
                "stress_evidence": (round(float(stress[index]), 4)
                                    if index < len(stress) else None),
                "interpretation": "REVIEW_PROMPT_NOT_CONFIRMED_ERROR",
            }
            if normalized not in candidates or row["accuracy_evidence"] < candidates[normalized]["accuracy_evidence"]:
                candidates[normalized] = row
    return sorted(candidates.values(), key=lambda row: (row["accuracy_evidence"], row["word"]))[:limit]


def deterministic_feedback(item: dict) -> dict:
    """Create concise feedback from named evidence fields only."""
    scores = item.get("scores", {})
    completeness = item.get("completeness", {})
    fluency = item.get("evidence", {}).get("fluency", {})
    words = item.get("evidence", {}).get("word_review_prompts", [])[:3]
    coverage = completeness.get("coverage")
    long_pauses = fluency.get("long_pause_count")
    if (isinstance(scores.get("fluency"), (int, float)) and scores["fluency"] >= 4.6
            and isinstance(long_pauses, (int, float)) and long_pauses == 0):
        strength = {
            "text": "Your reading stayed continuous, with no measured long pauses interrupting the flow.",
            "evidence_refs": ["scores.fluency", "evidence.fluency.long_pause_count"],
        }
    elif isinstance(coverage, (int, float)) and coverage >= 0.97:
        strength = {
            "text": f"You covered {coverage:.0%} of the target passage, so most of the reading was captured clearly.",
            "evidence_refs": ["completeness.coverage"],
        }
    elif isinstance(scores.get("prosody"), (int, float)) and scores["prosody"] >= 4.2:
        strength = {
            "text": "Your prosody evidence was the strongest measured area, suggesting useful rhythm and intonation across the passage.",
            "evidence_refs": ["scores.prosody", "evidence.raw_multipa.prosody"],
        }
    elif isinstance(scores.get("fluency"), (int, float)):
        strength = {
            "text": "Your reading maintained a mostly continuous flow across the passage.",
            "evidence_refs": ["scores.fluency", "evidence.fluency.pause_ratio"],
        }
    else:
        strength = {
            "text": "The recording provided enough measured speech evidence for a partial review.",
            "evidence_refs": ["scorability_status"],
        }

    comparable = {name: value for name, value in scores.items()
                  if name in {"pronunciation", "fluency", "prosody", "completeness"}
                  and isinstance(value, (int, float))}
    priority = min(comparable, key=comparable.get) if comparable else None
    if (isinstance(long_pauses, (int, float)) and long_pauses >= 3
            and isinstance(scores.get("fluency"), (int, float))):
        priority = "fluency"
    elif (isinstance(scores.get("pronunciation"), (int, float))
          and isinstance(scores.get("prosody"), (int, float))
          and abs(scores["pronunciation"] - scores["prosody"]) <= 0.05):
        priority = "prosody"
    if priority == "pronunciation" and words:
        labels = ", ".join(row["word"] for row in words)
        focus = {
            "text": f"The model found lower relative pronunciation evidence for {labels}. Treat these as review prompts, not confirmed errors.",
            "evidence_refs": ["evidence.word_review_prompts", "scores.pronunciation"],
        }
        practice = {
            "text": f"Read the sentence containing {words[0]['word']} once slowly, then repeat it at your natural pace and compare the two recordings.",
            "evidence_refs": ["evidence.word_review_prompts.0"],
        }
    elif priority == "fluency":
        longest = fluency.get("longest_pause_sec")
        detail = f" The longest measured pause was {longest:.2f} seconds." if isinstance(longest, (int, float)) else ""
        focus = {
            "text": "A few pauses interrupted the flow more than the surrounding speech." + detail,
            "evidence_refs": ["evidence.fluency.long_pause_count", "evidence.fluency.longest_pause_sec"],
        }
        practice = {
            "text": "Mark short phrase groups in the passage, then read each group in one breath before joining them together.",
            "evidence_refs": ["evidence.fluency.mean_length_of_run_words"],
        }
    elif priority == "prosody":
        focus = {
            "text": "Rhythm and stress evidence varied more than your strongest criterion, so phrasing is the best next refinement.",
            "evidence_refs": ["scores.prosody", "evidence.raw_multipa.prosody"],
        }
        practice = {
            "text": "Underline the key word in each phrase, then repeat the passage while giving those words slightly more stress.",
            "evidence_refs": ["evidence.raw_multipa.prosody"],
        }
    elif priority == "completeness":
        focus = {
            "text": "Some target spans were not matched confidently. This may include ASR uncertainty and is not a confirmed reading error.",
            "evidence_refs": ["completeness.possible_asr_uncertainty"],
        }
        practice = {
            "text": "Replay the uncertain spans and record them once more while keeping every target word visible.",
            "evidence_refs": ["completeness.possible_asr_uncertainty"],
        }
    else:
        focus = {
            "text": "No unsupported weakness was added. Use the evidence explorer to choose a small refinement.",
            "evidence_refs": [],
        }
        practice = {
            "text": "Record one more reading and compare its pausing and target coverage with this attempt.",
            "evidence_refs": ["scores", "completeness.coverage"],
        }
    return {
        "engine": "DETERMINISTIC_MEASURED_EVIDENCE_V1",
        "llm_used": False,
        "strength": strength,
        "focus_next": focus,
        "try_this": practice,
        "grammar_or_vocabulary_comment": False,
        "accent_shaming": False,
    }


def build_demo_cache(root: Path, destination: Path | None = None) -> dict:
    """Build a genuine machine-only cache from the completed P2.5 inference."""
    frozen = verify_frozen_scorer(root)
    prediction_path = root / ".local/multipa/p25/run/frozen_predictions.json"
    evidence_path = root / ".local/multipa/p25/run/machine_evidence.json"
    predictions = _load(prediction_path)
    evidence = _load(evidence_path)
    if (set(predictions.get("validation_ids", [])) != set(DEMO_IDS)
            or predictions.get("validation_ratings_read") is not False
            or predictions.get("training_or_refitting_performed") is not False
            or predictions.get("holdout_processed") is not False):
        raise ValueError("P2.5 frozen prediction provenance is unsafe")
    summary = _load(root / "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json")
    summary_by_id = {item["pair_id"]: item for item in summary["items"]}
    evidence_by_id = {item["pair_id"]: item for item in evidence["items"]}
    prediction_by_id = {item["pair_id"]: item for item in predictions["predictions"]}
    target = load_competition_target(root)
    rows = []
    for pair_id in DEMO_IDS:
        prediction = prediction_by_id[pair_id]
        machine = evidence_by_id[pair_id]
        source = summary_by_id[pair_id]
        asr_path = root / f"assessment_runs/T001_p24_tournament_v1/asr/ASR_A_SMALL_EN/{pair_id}.json"
        asr = _load(asr_path)
        complete = align_completeness(
            target["scored_passage"], asr["transcript"], "ASR_A_SMALL_EN_COMPETITION_TARGET_V2")
        item = {
            "pair_id": pair_id,
            "display_name": DEMO_LABELS[pair_id],
            "source_mode": "FAST_DEMO_FROZEN_CACHE",
            "created_at_utc": datetime.fromtimestamp(
                prediction_path.stat().st_mtime, timezone.utc).isoformat(),
            "genuine_frozen_inference": True,
            "fake_or_placeholder_score": False,
            "canonical_source": "RAW_COMPLETED_DUET",
            "audio_source_type": "RAW_CROPPED",
            "quality_gate": source["quality_gate"],
            "scorability_status": source["scorability_status"],
            "holdout": False,
            "raw_duet_sha256": source["raw_duet_sha256"],
            "model_input_ref": source["model_input_ref"],
            "model_input_sha256": source["model_input_sha256"],
            "asr_evidence_sha256": machine["asr_evidence_sha256"],
            "target_profile_sha256": TARGET_PROFILE_SHA256,
            "target_topic": target["topic"],
            "scores": {
                "pronunciation": prediction["pronunciation"],
                "fluency": prediction["fluency"],
                "prosody": prediction["prosody"],
                "completeness": round(1 + 4 * complete["coverage"], 4),
            },
            "criterion_status": {
                "pronunciation": "PRELIMINARY",
                "fluency": "USABLE",
                "prosody": "PRELIMINARY",
                "completeness": "USABLE",
            },
            "completeness": {
                "coverage": complete["coverage"],
                "matched_word_count": len(complete["matched_sequence"]),
                "possible_asr_uncertainty": [row["word"] for row in complete["omissions"]],
                "asr_insertions": [row["word"] for row in complete["insertions"]],
                "likely_omissions": [],
                "warning": complete["warning"],
            },
            "target_text": target["scored_passage"],
            "transcript": asr["transcript"],
            "evidence": {
                "fluency": {key: machine["fluency_features"].get(key) for key in (
                    "speech_rate_wpm", "articulation_rate_wpm", "pause_count",
                    "long_pause_count", "longest_pause_sec", "mean_pause_duration_sec",
                    "mean_length_of_run_words", "pause_ratio", "phonation_ratio")},
                "raw_multipa": prediction["raw_multipa"],
                "word_review_prompts": _word_evidence(prediction["raw_multipa_chunks"]),
                "asr_model": asr["model_id"],
                "asr_revision": asr["revision"],
            },
            "model_versions": {
                "multipa_source_commit": MULTIPA_COMMIT,
                "multipa_checkpoint_sha256": CHECKPOINT_SHA256,
                "asr": asr["model_id"],
                "asr_revision": asr["revision"],
            },
            "frozen_hashes": frozen,
            "machine_intelligibility": None,
            "overall_score": None,
            "model_failures": [],
        }
        item["feedback"] = deterministic_feedback(item)
        validate_deterministic_feedback(item)
        rows.append(item)
    cache = {
        "version": CACHE_VERSION,
        "created_at_utc": _now(),
        "demo_ids": list(DEMO_IDS),
        "frozen_hashes": frozen,
        "target_profile_sha256": TARGET_PROFILE_SHA256,
        "items": rows,
        "refit_performed": False,
        "machine_intelligibility": None,
        "overall_score": None,
        "holdout_processed": False,
    }
    destination = destination or root / CACHE_NAME
    _write(destination, cache)
    return validate_demo_cache(root, cache)


def offline_readiness(root: Path) -> dict:
    paths = {
        "multipa_python": root / ".local/multipa/venv/Scripts/python.exe",
        "multipa_source": root / ".local/multipa/source",
        "hubert": root / ".local/multipa/models/hubert_base_ls960.pt",
        "roberta": root / ".local/multipa/models/roberta.base",
        "checkpoint": root / ".local/multipa/models/model_assessment_val9_r1/model_assessment_val9_r1/PRO/best",
        "multipa_whisper": root / ".local/multipa/whisper_cache",
        "small_en": Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small.en",
    }
    available = {key: path.exists() for key, path in paths.items()}
    runtime_dependencies = {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
        "silero_vad": importlib.util.find_spec("silero_vad") is not None,
    }
    checkpoint_ok = (paths["checkpoint"].is_file()
                     and sha256_file(paths["checkpoint"]) == CHECKPOINT_SHA256)
    return {
        "ready": all(available.values()) and all(runtime_dependencies.values()) and checkpoint_ok,
        "assets": available,
        "runtime_dependencies": runtime_dependencies,
        "checkpoint_hash_verified": checkpoint_ok,
        "remote_services_required": [],
    }


def _run_live_multipa(root: Path, request: dict, work_dir: Path) -> list[dict]:
    local = root / ".local/multipa"
    request_path = work_dir / "multipa_request.json"
    output_path = work_dir / "multipa_output.json"
    _write(request_path, request)
    python = local / "venv/Scripts/python.exe"
    source = local / "source"
    checkpoint = local / "models/model_assessment_val9_r1/model_assessment_val9_r1/PRO/best"
    if sha256_file(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError("Frozen MultiPA checkpoint changed")
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != MULTIPA_COMMIT:
        raise ValueError("Frozen MultiPA source revision changed")
    command = [
        str(python), str(root / "scripts/p24d_multipa_worker.py"),
        "--request", str(request_path), "--output", str(output_path),
        "--source", str(source),
        "--hubert", str(local / "models/hubert_base_ls960.pt"),
        "--roberta", str(local / "models/roberta.base"),
        "--checkpoint", str(checkpoint),
        "--whisper-cache", str(local / "whisper_cache"),
    ]
    subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
    return _load(output_path)["items"]


def run_live_analysis(root: Path, duet_path: Path, work_dir: Path,
                      progress: Callable[[str], None] | None = None) -> dict:
    """Run actual Phase 1, local ASR, and the frozen scorer for a new Duet."""
    frozen = verify_frozen_scorer(root)
    if not offline_readiness(root)["ready"]:
        raise RuntimeError("Required offline scoring assets are unavailable")
    notify = progress or (lambda _message: None)
    work_dir.mkdir(parents=True, exist_ok=True)
    duet_sha256 = sha256_file(duet_path)
    notify("Video received")
    profile = build_template_profile(
        root / "data/templates/T001/original.mp4",
        root / ".local/competition_demo/template_profile",
        "T001", load_config(), force=False)
    phase1 = run_profiled(profile, duet_path, work_dir / "phase1", load_config(), "T001-LIVE")
    if (phase1.get("status") != "ok"
            or phase1.get("scorability_status") != "SCORABLE_CLEAN"
            or not phase1.get("learner_segments")):
        return {
            "version": CACHE_VERSION,
            "pair_id": "T001-LIVE",
            "display_name": "Uploaded Duet",
            "source_mode": "LIVE_ANALYSIS",
            "raw_duet_sha256": duet_sha256,
            "status": "NOT_SCORABLE",
            "reason_codes": phase1.get("quality_gate_reasons", []) + phase1.get("scorability_reasons", []),
            "scores": {},
            "machine_intelligibility": None,
            "overall_score": None,
            "holdout": False,
            "holdout_processed": False,
        }
    notify("Learner speech identified")
    intervals = phase1["learner_segments"]
    turn = {
        "turn_id": "T001",
        "start_sec": min(row["start"] for row in intervals),
        "end_sec": max(row["end"] for row in intervals),
        "learner_intervals": [{"start": row["start"], "end": row["end"]} for row in intervals],
    }
    audio_path = work_dir / "raw_learner_audio.wav"
    prepare_turn_audio(duet_path, turn, audio_path)
    notify("Audio quality verified")
    asr_config = yaml.safe_load((root / "p2_config.yaml").read_text(encoding="utf-8"))["asr"]
    asr = FasterWhisperBackend(**asr_config)
    transcript = asr.transcribe(audio_path, turn["start_sec"], turn["end_sec"], turn["learner_intervals"])
    fluency_evidence = measure_fluency(turn, transcript["words"])
    target = load_competition_target(root)
    frozen_multipa_target = _load(root / "task_profiles/T001_target_text_v1.json")["confirmed_text"]
    completeness = align_completeness(
        target["scored_passage"], transcript["verbatim_transcript"], "ASR_A_SMALL_EN_LIVE")
    notify("Fluency measured")
    notify("Reading coverage checked")
    plan = _load(root / "p25_frozen_mini_validation_plan_v1.json")
    scores: dict[str, float] = {
        "fluency": apply_mapping(plan["criteria"]["fluency"]["mapping"], fluency_evidence),
        "completeness": round(1 + 4 * completeness["coverage"], 4),
    }
    model_failures = []
    raw_multipa = None
    raw_chunks: list[dict] = []
    try:
        # The title correction applies only to Reading Completeness. MultiPA keeps
        # the exact v1 closed-response target used by the frozen scorer.
        chunks = segment_closed_response(transcript["words"], frozen_multipa_target)
        if not chunks or not all(chunk["valid_for_scoring"] for chunk in chunks):
            raise ValueError("Target alignment is not reliable enough for MultiPA")
        for chunk in chunks:
            local_start = chunk["start_sec"] - turn["start_sec"]
            local_end = chunk["end_sec"] - turn["start_sec"]
            chunk_path = work_dir / "chunks" / f"chunk_{chunk['chunk_index']:02d}.wav"
            write_wav_slice(audio_path, chunk_path, local_start, local_end)
            chunk["wav_path"] = str(chunk_path.resolve())
            chunk["wav_sha256"] = sha256_file(chunk_path)
        request = {
            "mode": "PRETRAINED_INFERENCE_ONLY",
            "plan_sha256": frozen["p25_plan_sha256"],
            "items": [{"pair_id": "T001-LIVE", "chunks": chunks}],
            "neural_training_or_finetuning": False,
            "validation_ratings_read": False,
            "holdout_processed": False,
        }
        raw_chunks = _run_live_multipa(root, request, work_dir)
        aggregate = aggregate_video(raw_chunks, len(chunks))
        if not aggregate["valid"]:
            raise RuntimeError("MultiPA did not return every planned chunk")
        raw_multipa = aggregate["raw_pretrained_score"]
        scores["pronunciation"] = apply_fitted_mapping(
            plan["criteria"]["pronunciation"]["mapping"],
            "multipa_accuracy", raw_multipa["accuracy"])
        scores["prosody"] = apply_fitted_mapping(
            plan["criteria"]["prosody"]["mapping"],
            "multipa_prosody", raw_multipa["prosody"])
        notify("Pronunciation analyzed")
        notify("Prosody analyzed")
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        model_failures.append({
            "criteria": ["pronunciation", "prosody"],
            "public_message": "Pronunciation and prosody assessment are unavailable for this recording.",
            "internal_reason": str(exc),
        })
    item = {
        "version": CACHE_VERSION,
        "pair_id": "T001-LIVE",
        "display_name": "Uploaded Duet",
        "source_mode": "LIVE_ANALYSIS",
        "status": "COMPLETE" if not model_failures else "PARTIAL",
        "created_at_utc": _now(),
        "genuine_frozen_inference": True,
        "fake_or_placeholder_score": False,
        "canonical_source": "RAW_COMPLETED_DUET",
        "audio_source_type": "RAW_CROPPED",
        "raw_duet_sha256": duet_sha256,
        "target_profile_sha256": TARGET_PROFILE_SHA256,
        "target_topic": target["topic"],
        "quality_gate": phase1["quality_gate"],
        "scorability_status": phase1["scorability_status"],
        "holdout": False,
        "scores": scores,
        "criterion_status": {
            "pronunciation": "PRELIMINARY" if "pronunciation" in scores else "UNAVAILABLE",
            "fluency": "USABLE",
            "prosody": "PRELIMINARY" if "prosody" in scores else "UNAVAILABLE",
            "completeness": "USABLE",
        },
        "completeness": {
            "coverage": completeness["coverage"],
            "matched_word_count": len(completeness["matched_sequence"]),
            "possible_asr_uncertainty": [row["word"] for row in completeness["omissions"]],
            "asr_insertions": [row["word"] for row in completeness["insertions"]],
            "likely_omissions": [],
            "warning": completeness["warning"],
        },
        "target_text": target["scored_passage"],
        "transcript": transcript["verbatim_transcript"],
        "evidence": {
            "fluency": {key: fluency_evidence.get(key) for key in (
                "speech_rate_wpm", "articulation_rate_wpm", "pause_count",
                "long_pause_count", "longest_pause_sec", "mean_pause_duration_sec",
                "mean_length_of_run_words", "pause_ratio", "phonation_ratio")},
            "raw_multipa": raw_multipa,
            "word_review_prompts": _word_evidence(raw_chunks),
            "asr_model": "Systran/faster-whisper-small.en",
        },
        "frozen_hashes": frozen,
        "machine_intelligibility": None,
        "overall_score": None,
        "model_failures": model_failures,
        "holdout_processed": False,
    }
    item["feedback"] = deterministic_feedback(item)
    validate_deterministic_feedback(item)
    _write(work_dir / "result.json", item)
    notify("Evidence-based feedback prepared")
    return item
