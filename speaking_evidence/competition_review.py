"""Manual, hash-bound GPT review bundles for the competition demo.

This module never calls ChatGPT or any remote service. It exports local review
materials and strictly validates a human-imported structured review.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from speaking_evidence.competition_demo import (
    CACHE_NAME,
    DEMO_IDS,
    TARGET_PROFILE_SHA256,
    load_demo_cache,
)


REVIEW_VERSION = "competition-gpt-review-v1"
PROMPT_NAME = "competition_gpt_review_prompt_v1.txt"
PROMPT_SHA256 = "415354a8d9c5fe391587d02209264b49b88fcf2316df9b3eab820f0fb61111aa"
REVIEW_STORE = "runs/competition_gpt_review/imported"
REQUIRED_REVIEW_FIELDS = {
    "review_version", "video_id", "video_input_sha256", "scorer_fingerprint",
    "target_profile_sha256", "review_prompt_sha256", "review_source",
    "review_timestamp_utc", "strength", "focus_next", "practice_suggestion",
    "review_words", "supporting_observations", "uncertainty_notes",
    "score_contradiction_flags", "safe_for_student_display",
}


class ReviewValidationError(ValueError):
    """Raised when a manual GPT review is stale, unsupported, or malformed."""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def scorer_fingerprint(item: dict) -> str:
    payload = {
        "criterion_status": item["criterion_status"],
        "frozen_hashes": item.get("frozen_hashes"),
        "model_versions": item["model_versions"],
        "scores": item["scores"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(canonical)


def _machine_evidence(item: dict) -> dict:
    raw = item.get("evidence", {}).get("raw_multipa") or {}
    fluency = item.get("evidence", {}).get("fluency") or {}
    return {
        "video_id": item["pair_id"],
        "input_sha256": item["model_input_sha256"],
        "scorer_fingerprint": scorer_fingerprint(item),
        "target_profile_sha256": item["target_profile_sha256"],
        "criterion_status": item["criterion_status"],
        "scores": {
            "pronunciation": item["scores"].get("pronunciation"),
            "fluency": item["scores"].get("fluency"),
            "prosody": item["scores"].get("prosody"),
            "reading_completeness": item["scores"].get("completeness"),
        },
        "pronunciation_evidence": {
            "raw_multipa_accuracy": raw.get("accuracy"),
            "word_review_prompts": item.get("evidence", {}).get("word_review_prompts", []),
        },
        "fluency_evidence": {
            key: fluency.get(key) for key in (
                "speech_rate_wpm", "articulation_rate_wpm", "pause_count",
                "long_pause_count", "longest_pause_sec", "mean_pause_duration_sec",
                "mean_length_of_run_words", "pause_ratio", "phonation_ratio")
        },
        "prosody_evidence": {
            "raw_multipa_prosody": raw.get("prosody"),
            "word_stress_prompts": [
                {"word": row.get("word"), "stress_evidence": row.get("stress_evidence")}
                for row in item.get("evidence", {}).get("word_review_prompts", [])
                if row.get("stress_evidence") is not None
            ],
        },
        "completeness_evidence": item["completeness"],
        "target_topic": item.get("target_topic"),
        "target_text": item["target_text"],
        "transcript": item["transcript"],
        "model_versions": item["model_versions"],
        "model_failures": item.get("model_failures", []),
        "machine_intelligibility": None,
        "overall_score": None,
    }


def export_review_bundle(root: Path, pair_id: str, destination: Path | None = None) -> Path:
    if pair_id not in DEMO_IDS:
        raise ValueError("Only frozen development competition demos may be exported")
    item = load_demo_cache(root, pair_id, verify_media=True)
    destination = destination or root / "runs/competition_gpt_review" / pair_id
    destination.mkdir(parents=True, exist_ok=True)
    source_audio = root / "assessment_runs/T001_p24_tournament_v1" / item["model_input_ref"]
    audio_path = destination / "learner_audio.wav"
    shutil.copy2(source_audio, audio_path)
    (destination / "target_text.txt").write_text(
        f"Topic: {item['target_topic']}\n\nScored passage:\n{item['target_text']}\n", encoding="utf-8")
    (destination / "learner_transcript.txt").write_text(item["transcript"] + "\n", encoding="utf-8")
    evidence = _machine_evidence(item)
    _write(destination / "machine_evidence.json", evidence)
    prompt_path = root / PROMPT_NAME
    if _sha256_file(prompt_path) != PROMPT_SHA256:
        raise ReviewValidationError("GPT review prompt changed")
    shutil.copy2(prompt_path, destination / "review_prompt.txt")
    manifest = {
        "bundle_version": REVIEW_VERSION,
        "video_id": pair_id,
        "split": "DEVELOPMENT",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "video_input_sha256": item["model_input_sha256"],
        "learner_audio_sha256": _sha256_file(audio_path),
        "scorer_fingerprint": scorer_fingerprint(item),
        "target_profile_sha256": TARGET_PROFILE_SHA256,
        "review_prompt_sha256": PROMPT_SHA256,
        "machine_evidence_sha256": _sha256_file(destination / "machine_evidence.json"),
        "teacher_ratings_included": False,
        "validation_labels_included": False,
        "holdout_included": False,
        "chatgpt_automation_used": False,
    }
    _write(destination / "bundle_manifest.json", manifest)
    return destination


def _evidence_ref_exists(evidence: dict, reference: str) -> bool:
    value: object = evidence
    for part in reference.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return False
    return True


def _validate_text(text: object, field: str, max_words: int = 42) -> str:
    if not isinstance(text, str) or not text.strip() or len(text.split()) > max_words:
        raise ReviewValidationError(f"Invalid review text: {field}")
    lowered = text.lower()
    forbidden = ("cefr", "ielts", "intelligibility score", "overall score",
                 "vietnamese accent", "grammar", "vocabulary", "confidence")
    if any(token in lowered for token in forbidden):
        raise ReviewValidationError(f"Unsupported student claim: {field}")
    if (re.search(r"\b(?:score|rating)\s*(?:of|is|=|:)\s*\d", lowered)
            or re.search(r"\b\d(?:\.\d+)?\s*/\s*5\b", lowered)):
        raise ReviewValidationError(f"Review attempts to replace a score: {field}")
    return text.strip()


def validate_review_payload(root: Path, pair_id: str, payload: dict) -> dict:
    if set(payload) != REQUIRED_REVIEW_FIELDS:
        raise ReviewValidationError("Review fields do not match the frozen schema")
    item = load_demo_cache(root, pair_id, verify_media=True)
    expected = {
        "review_version": REVIEW_VERSION,
        "video_id": pair_id,
        "video_input_sha256": item["model_input_sha256"],
        "scorer_fingerprint": scorer_fingerprint(item),
        "target_profile_sha256": TARGET_PROFILE_SHA256,
        "review_prompt_sha256": PROMPT_SHA256,
        "review_source": "CHATGPT_MANUAL_REVIEW",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ReviewValidationError(f"Stale or incorrect review provenance: {key}")
    try:
        timestamp = datetime.fromisoformat(str(payload["review_timestamp_utc"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewValidationError("Invalid review timestamp") from exc
    if timestamp.tzinfo is None:
        raise ReviewValidationError("Review timestamp must include a timezone")
    if payload["safe_for_student_display"] is not True:
        raise ReviewValidationError("Review is not approved for student display")
    if not isinstance(payload["score_contradiction_flags"], list) or payload["score_contradiction_flags"]:
        raise ReviewValidationError("Score contradiction requires human resolution")
    for field in ("strength", "focus_next", "practice_suggestion"):
        payload[field] = _validate_text(payload[field], field)
    evidence = _machine_evidence(item)
    allowed_words = {
        row["word"].lower() for row in evidence["pronunciation_evidence"]["word_review_prompts"]
        if isinstance(row.get("word"), str)
    }
    if (not isinstance(payload["review_words"], list)
            or any(not isinstance(word, str) or word.lower() not in allowed_words
                   for word in payload["review_words"])):
        raise ReviewValidationError("Review words are not supported by frozen word evidence")
    observations = payload["supporting_observations"]
    if not isinstance(observations, list) or not observations:
        raise ReviewValidationError("At least one supporting observation is required")
    for index, observation in enumerate(observations):
        if set(observation) != {"text", "evidence_refs"}:
            raise ReviewValidationError("Supporting observation schema is invalid")
        observation["text"] = _validate_text(observation["text"], f"observation_{index}")
        refs = observation["evidence_refs"]
        if (not isinstance(refs, list) or not refs
                or any(not isinstance(ref, str) or not _evidence_ref_exists(evidence, ref) for ref in refs)):
            raise ReviewValidationError("Supporting observation cites missing evidence")
    for field in ("uncertainty_notes", "score_contradiction_flags"):
        if not isinstance(payload[field], list) or any(not isinstance(value, str) for value in payload[field]):
            raise ReviewValidationError(f"Invalid list field: {field}")
    return payload


def import_review(root: Path, source: Path, pair_id: str | None = None) -> Path:
    raw = source.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    pair_id = pair_id or payload.get("video_id")
    if pair_id not in DEMO_IDS:
        raise ReviewValidationError("Review video is not a permitted competition demo")
    payload = validate_review_payload(root, pair_id, payload)
    artifact = {
        "artifact_version": "competition-imported-gpt-review-v1",
        "video_id": pair_id,
        "imported_at_utc": datetime.now(timezone.utc).isoformat(),
        "imported_payload_sha256": _sha256_bytes(raw),
        "review": payload,
        "official_scores_overridden": False,
        "chatgpt_automation_used": False,
    }
    destination = root / REVIEW_STORE / f"{pair_id}.json"
    _write(destination, artifact)
    return destination


def load_review_feedback(root: Path, item: dict) -> tuple[dict, dict] | None:
    path = root / REVIEW_STORE / f"{item['pair_id']}.json"
    if not path.is_file():
        return None
    try:
        artifact = _load(path)
        if (artifact.get("artifact_version") != "competition-imported-gpt-review-v1"
                or artifact.get("video_id") != item["pair_id"]
                or artifact.get("official_scores_overridden") is not False):
            return None
        review = validate_review_payload(root, item["pair_id"], artifact["review"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ReviewValidationError):
        return None
    feedback = {
        "engine": "GPT_REVIEWED_PERSONALIZED_FEEDBACK_V1",
        "llm_used": True,
        "strength": {"text": review["strength"], "evidence_refs": []},
        "focus_next": {"text": review["focus_next"], "evidence_refs": []},
        "try_this": {"text": review["practice_suggestion"], "evidence_refs": []},
        "review_words": review["review_words"],
        "uncertainty_notes": review["uncertainty_notes"],
        "grammar_or_vocabulary_comment": False,
        "accent_shaming": False,
    }
    try:
        provenance_path = str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        provenance_path = path.name
    provenance = {
        "feedback_source": "GPT_REVIEWED_IMPORTED",
        "review_version": REVIEW_VERSION,
        "review_source": review["review_source"],
        "review_timestamp_utc": review["review_timestamp_utc"],
        "imported_payload_sha256": artifact["imported_payload_sha256"],
        "path": provenance_path,
    }
    return feedback, provenance


def selected_feedback(root: Path, item: dict) -> tuple[dict, dict]:
    reviewed = load_review_feedback(root, item)
    if reviewed is not None:
        return reviewed
    return item["feedback"], {
        "feedback_source": "DETERMINISTIC_FALLBACK",
        "review_version": None,
        "review_source": None,
    }
