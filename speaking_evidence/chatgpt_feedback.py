"""Automatic, text-only ChatGPT feedback with strict frozen-score boundaries."""
from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

from speaking_evidence.chatgpt_auth import (
    ChatGPTAuthManager,
    ChatGPTConnectionError,
    RESPONSES_ENDPOINT,
    app_data_root,
)


AUTO_FEEDBACK_VERSION = "competition-auto-feedback-v1"
AUTO_PROMPT_VERSION = "nckh12-auto-feedback-prompt-v1"
FEEDBACK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "strength": {"type": "string"},
        "focus_next": {"type": "string"},
        "practice_suggestion": {"type": "string"},
        "review_words": {"type": "array", "items": {"type": "string"}},
        "supporting_observations": {"type": "array", "items": {"type": "string"}},
        "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
        "score_contradiction_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "strength", "focus_next", "practice_suggestion", "review_words",
        "supporting_observations", "uncertainty_notes", "score_contradiction_flags",
    ],
}


class AutomaticFeedbackError(RuntimeError):
    def __init__(self, code: str, public_message: str =
                 "Personalized AI review was unavailable. Evidence-based feedback is shown instead."):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def feedback_cache_root() -> Path:
    return app_data_root() / "feedback_cache" / AUTO_FEEDBACK_VERSION


def build_text_evidence(result: dict) -> dict:
    """Create the only payload allowed to leave the local scorer.

    It is intentionally allowlisted. Media, local paths, human labels, split
    metadata, and research-only fields cannot enter this payload.
    """
    scores = result.get("scores", {})
    evidence = result.get("evidence", {})
    fluency = evidence.get("fluency", {})
    complete = result.get("completeness", {})
    raw_multipa = evidence.get("raw_multipa") or {}
    word_prompts = [
        {
            "word": row.get("word"),
            "relative_accuracy_evidence": row.get("accuracy_evidence"),
            "interpretation": "WORD_TO_REVIEW_NOT_CONFIRMED_ERROR",
        }
        for row in evidence.get("word_review_prompts", [])[:3]
        if isinstance(row.get("word"), str)
    ]
    payload = {
        "task": "Controlled reading of the confirmed T001 passage",
        "rubric": {
            "pronunciation": "Sound accuracy and clarity; preliminary machine evidence",
            "fluency": "Flow, continuity and pausing",
            "prosody": "Stress, rhythm and intonation; preliminary machine evidence",
            "reading_completeness": "ASR-assisted target coverage",
        },
        "frozen_score_rule": "Numeric scores are frozen. Do not replace, recompute, or contradict them.",
        "target_text": result.get("target_text", ""),
        "learner_transcript": result.get("transcript", ""),
        "criterion_scores": {
            "pronunciation": scores.get("pronunciation"),
            "fluency": scores.get("fluency"),
            "prosody": scores.get("prosody"),
            "reading_completeness_percent": (
                round(float(complete.get("coverage")) * 100, 2)
                if isinstance(complete.get("coverage"), (int, float)) else None
            ),
        },
        "criterion_status": deepcopy(result.get("criterion_status", {})),
        "pronunciation_evidence": {"review_words": word_prompts},
        "fluency_evidence": {
            "words_per_minute": fluency.get("speech_rate_wpm"),
            "pause_count": fluency.get("pause_count"),
            "long_pause_count": fluency.get("long_pause_count"),
            "longest_pause_seconds": fluency.get("longest_pause_sec"),
            "mean_words_per_speech_run": fluency.get("mean_length_of_run_words"),
        },
        "prosody_evidence": {
            "pretrained_relative_evidence": raw_multipa.get("prosody"),
            "interpretation": "FORMATIVE_PRELIMINARY_EVIDENCE",
        },
        "completeness_evidence": {
            "matched_target_words": complete.get("matched_word_count"),
            "possible_asr_uncertainty": complete.get("possible_asr_uncertainty", [])[:12],
            "warning": "ASR uncertainty is not a confirmed learner omission.",
        },
    }
    def keys(value: object) -> list[str]:
        if isinstance(value, dict):
            return [str(key).lower() for key in value] + [
                nested for row in value.values() for nested in keys(row)
            ]
        if isinstance(value, list):
            return [nested for row in value for nested in keys(row)]
        return []

    forbidden = ("teacher", "human_rating", "validation_rating", "holdout",
                 "audio", "video", "local_path")
    if any(any(token in key for token in forbidden) for key in keys(payload)):
        raise AutomaticFeedbackError("unsafe_evidence_payload")
    return payload


def scorer_hash(result: dict) -> str:
    frozen = result.get("frozen_hashes", {})
    if not isinstance(frozen, dict) or not frozen:
        raise AutomaticFeedbackError("missing_scorer_provenance")
    return _sha(frozen)


def input_hash(result: dict) -> str:
    value = result.get("raw_duet_sha256") or result.get("model_input_sha256")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise AutomaticFeedbackError("missing_input_hash")
    return value.lower()


def cache_identity(result: dict, model_slug: str) -> dict:
    evidence = build_text_evidence(result)
    return {
        "input_sha256": input_hash(result),
        "scorer_sha256": scorer_hash(result),
        "target_sha256": result.get("target_profile_sha256"),
        "evidence_sha256": _sha(evidence),
        "prompt_version": AUTO_PROMPT_VERSION,
        "model_slug": model_slug,
    }


def cache_key(identity: dict) -> str:
    return _sha(identity)


def _feedback_path(identity: dict, root: Path | None = None) -> Path:
    return (root or feedback_cache_root()) / f"{cache_key(identity)}.json"


def validate_feedback(payload: dict, evidence: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) != set(FEEDBACK_SCHEMA["required"]):
        raise AutomaticFeedbackError("invalid_feedback_schema")
    for key in ("strength", "focus_next", "practice_suggestion"):
        if not isinstance(payload[key], str) or not payload[key].strip() or len(payload[key].split()) > 45:
            raise AutomaticFeedbackError("invalid_feedback_schema")
    for key in ("review_words", "supporting_observations", "uncertainty_notes",
                "score_contradiction_flags"):
        if not isinstance(payload[key], list) or not all(isinstance(row, str) for row in payload[key]):
            raise AutomaticFeedbackError("invalid_feedback_schema")
    if payload["score_contradiction_flags"]:
        raise AutomaticFeedbackError("numeric_score_override_rejected")
    allowed_words = {
        row["word"].lower() for row in evidence["pronunciation_evidence"]["review_words"]
    }
    if any(word.lower() not in allowed_words for word in payload["review_words"]):
        raise AutomaticFeedbackError("unsupported_review_word")
    combined = " ".join(
        [payload["strength"], payload["focus_next"], payload["practice_suggestion"]]
        + payload["supporting_observations"] + payload["uncertainty_notes"]
    ).lower()
    forbidden = ("overall score", "intelligibility score", "cefr", "ielts",
                 "vietnamese accent", "non-native accent", "grammar error", "vocabulary error")
    if any(term in combined for term in forbidden) or re.search(r"\b[0-5](?:\.\d+)?\s*/\s*5\b", combined):
        raise AutomaticFeedbackError("unsupported_feedback_claim")
    return payload


def prompt_for(evidence: dict) -> list[dict]:
    instruction = (
        "Create concise, student-friendly formative feedback grounded only in the supplied evidence. "
        "Give one real strength, one highest-value focus, and one concrete practice action. "
        "Do not change or restate numeric scores. Do not create Overall or Intelligibility scores. "
        "Do not diagnose grammar, vocabulary, accent, or phonemes. ASR uncertainty and low relative "
        "model evidence are review prompts, not confirmed learner errors. Return the required JSON only."
    )
    return [
        {"role": "developer", "content": instruction},
        {"role": "user", "content": json.dumps(evidence, ensure_ascii=False, sort_keys=True)},
    ]


def _response_text(response: dict) -> str:
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
    return ""


def _error_code(payload: dict, default: str) -> str:
    error = payload.get("error")
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("error"), dict):
        return str(response["error"].get("code") or default)
    return default


def stream_structured_feedback(access_token: str, model_slug: str, evidence: dict,
                               client_factory: Callable[[], httpx.Client] | None = None) -> dict:
    body = {
        "model": model_slug,
        "input": prompt_for(evidence),
        "store": False,
        "stream": True,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "nckh12_formative_feedback",
                "strict": True,
                "schema": FEEDBACK_SCHEMA,
            }
        },
    }
    factory = client_factory or (lambda: httpx.Client())
    terminal = None
    deltas: list[str] = []
    try:
        with factory() as client:
            with client.stream("POST", RESPONSES_ENDPOINT,
                               headers={"Authorization": f"Bearer {access_token}"},
                               json=body, timeout=90) as response:
                if response.status_code >= 400:
                    try:
                        code = _error_code(response.json(), f"http_{response.status_code}")
                    except ValueError:
                        code = f"http_{response.status_code}"
                    raise AutomaticFeedbackError(code)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    event = json.loads(data)
                    event_type = event.get("type")
                    if event_type == "response.output_text.delta" and isinstance(event.get("delta"), str):
                        deltas.append(event["delta"])
                    elif event_type == "response.completed":
                        terminal = event
                    elif event_type == "response.failed":
                        raise AutomaticFeedbackError(_error_code(event, "response_failed"))
                    elif event_type == "response.incomplete":
                        raise AutomaticFeedbackError("response_incomplete")
    except AutomaticFeedbackError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise AutomaticFeedbackError("network_or_stream_failure") from exc
    if terminal is None:
        raise AutomaticFeedbackError("stream_interrupted")
    raw = _response_text(terminal.get("response", {})) or "".join(deltas)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AutomaticFeedbackError("invalid_feedback_json") from exc
    return validate_feedback(payload, evidence)


def _to_display_feedback(payload: dict) -> dict:
    return {
        "engine": "CHATGPT_AUTOMATIC_TEXT_REVIEW_V1",
        "llm_used": True,
        "strength": {"text": payload["strength"], "evidence_refs": []},
        "focus_next": {"text": payload["focus_next"], "evidence_refs": []},
        "try_this": {"text": payload["practice_suggestion"], "evidence_refs": []},
        "review_words": payload["review_words"],
        "supporting_observations": payload["supporting_observations"],
        "uncertainty_notes": payload["uncertainty_notes"],
        "grammar_or_vocabulary_comment": False,
        "accent_shaming": False,
    }


def load_cached_feedback(result: dict, model_slug: str,
                         root: Path | None = None) -> tuple[dict, dict] | None:
    identity = cache_identity(result, model_slug)
    path = _feedback_path(identity, root)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if record.get("identity") != identity or record.get("cache_key") != cache_key(identity):
        return None
    evidence = build_text_evidence(result)
    try:
        validated = validate_feedback(record.get("feedback"), evidence)
    except AutomaticFeedbackError:
        return None
    return _to_display_feedback(validated), record["provenance"]


def purge_feedback_for_input(input_sha256: str, root: Path | None = None) -> int:
    """Delete private automatic feedback tied to removed user media."""
    directory = root or feedback_cache_root()
    if not directory.is_dir():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("identity", {}).get("input_sha256") == input_sha256:
            path.unlink()
            removed += 1
    return removed


def automatic_feedback(result: dict, auth: ChatGPTAuthManager | None = None,
                       cache_root: Path | None = None,
                       client_factory: Callable[[], httpx.Client] | None = None) -> tuple[dict, dict]:
    manager = auth or ChatGPTAuthManager()
    profile = manager.access_profile()
    model = profile.get("selected_model")
    if not isinstance(model, str):
        manager.discover_models()
        profile = manager.access_profile()
        model = profile.get("selected_model")
    if not isinstance(model, str):
        raise AutomaticFeedbackError("no_available_models")
    cached = load_cached_feedback(result, model, cache_root)
    if cached:
        feedback, provenance = cached
        provenance = {**provenance, "cache_hit": True}
        return feedback, provenance
    evidence = build_text_evidence(result)
    try:
        payload = stream_structured_feedback(
            profile["access_token"], model, evidence, client_factory=client_factory)
    except ChatGPTConnectionError as exc:
        raise AutomaticFeedbackError(exc.code) from exc
    identity = cache_identity(result, model)
    provenance = {
        "feedback_source": "CHATGPT_PLAN_AUTOMATIC_REVIEW",
        "review_version": AUTO_FEEDBACK_VERSION,
        "prompt_version": AUTO_PROMPT_VERSION,
        "model_slug": model,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cache_hit": False,
        "text_evidence_only": True,
        "audio_or_video_sent": False,
        "numeric_scores_replaced": False,
    }
    record = {
        "version": AUTO_FEEDBACK_VERSION,
        "cache_key": cache_key(identity),
        "identity": identity,
        "feedback": payload,
        "provenance": provenance,
    }
    path = _feedback_path(identity, cache_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    return _to_display_feedback(payload), provenance


def attach_automatic_feedback(result: dict, **kwargs: object) -> tuple[dict, str | None]:
    """Return a session-safe result; failure never changes the assessment."""
    enriched = deepcopy(result)
    try:
        feedback, provenance = automatic_feedback(enriched, **kwargs)
    except (AutomaticFeedbackError, ChatGPTConnectionError) as exc:
        return enriched, getattr(exc, "code", "automatic_feedback_unavailable")
    enriched["automatic_feedback"] = feedback
    enriched["automatic_feedback_provenance"] = provenance
    return enriched, None
