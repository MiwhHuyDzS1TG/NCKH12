"""Phase 3 input contract; this module does not generate learner feedback."""
from __future__ import annotations

from typing import Protocol

from speaking_evidence.p22 import DISCLAIMER

VERSION = "feedback-input-contract-v1"
CRITERIA = ("fluency", "pronunciation", "intelligibility", "completeness", "prosody")
SAFETY_RULES = (
    "Mention only evidence present in this contract.",
    "Do not invent pronunciation errors or turn ASR mismatches into learner errors.",
    "Do not make CEFR, B2, IELTS, native-likeness, or accent-reduction claims.",
    "Do not shame accents or require a native-speaker accent.",
    "Return at most a few actions: strengths, one priority improvement, and one next-practice action.",
)


class FutureLocalFeedbackAdapter(Protocol):
    """Interface a future local LLM adapter must implement."""

    def generate(self, contract: dict) -> dict:
        """Consume a validated contract and return a separately stored draft."""
        ...


def _calibrated_row(pair_id: str, calibration_summary: dict | None) -> dict | None:
    if not calibration_summary:
        return None
    if calibration_summary.get("labels") != DISCLAIMER:
        raise ValueError("Calibration summary lacks the required preliminary/proficiency disclaimers")
    if calibration_summary.get("holdout_processed") is not False:
        raise ValueError("Feedback input cannot use a holdout-fitted calibration")
    return next((row for row in calibration_summary.get("scores", [])
                 if row.get("pair_id") == pair_id), None)


def build_feedback_contract(evidence: dict, completeness: dict | None,
                            pronunciation: dict | None = None,
                            calibration_summary: dict | None = None) -> dict:
    """Build a measured-evidence-only Phase 3 input payload.

    Numeric scores can enter only through a valid saved calibration summary.
    The function produces no recommendations or learner-facing prose.
    """
    pair_id = evidence.get("pair_id")
    if evidence.get("holdout") is not False or evidence.get("scope") != "DEVELOPMENT_ONLY":
        raise ValueError("Feedback preparation accepts development evidence only")
    if evidence.get("audio_provenance", {}).get("canonical_source") != "RAW_COMPLETED_DUET":
        raise ValueError("Feedback evidence must originate from RAW_COMPLETED_DUET")
    turn = evidence["turns"][0]
    row = _calibrated_row(pair_id, calibration_summary)
    fluency = evidence.get("aggregate_fluency_evidence", {})
    words = turn.get("transcript", {}).get("words", [])
    probabilities = [word.get("probability") for word in words
                     if isinstance(word.get("probability"), (int, float))]
    acoustic = turn.get("acoustic", {})

    pronunciation_status = (
        pronunciation.get("status") if pronunciation else "PRONUNCIATION_EVIDENCE_PENDING"
    )
    payload = {
        "version": VERSION,
        "pair_id": pair_id,
        "status": "READY_FOR_FUTURE_FEEDBACK_ADAPTER" if row else "WAITING_FOR_HUMAN_CALIBRATION",
        "canonical_audio_source": "RAW_COMPLETED_DUET",
        "criteria": {
            "fluency": {
                "score": row.get("fluency") if row else None,
                "status": row.get("fluency_status", "DEVELOPMENT_PRELIMINARY")
                if row else "WAITING_FOR_HUMAN_CALIBRATION",
                "evidence": {key: fluency.get(key) for key in
                             ("pause_ratio", "long_pause_count", "longest_pause_sec",
                              "mean_length_of_run_words", "speech_rate_wpm",
                              "articulation_rate_wpm", "phonation_ratio")},
            },
            "pronunciation": {
                "score": row.get("pronunciation") if row else None,
                "status": pronunciation_status if not row or row.get("pronunciation") is None
                else "DEVELOPMENT_PRELIMINARY",
                "evidence": {
                    "analyzed_coverage": pronunciation.get("utterance", {}).get("analyzed_coverage")
                    if pronunciation else None,
                    "error_diagnoses_confirmed": False,
                    "asr_mismatch_is_pronunciation_error": False,
                },
            },
            "intelligibility": {
                "score": row.get("intelligibility") if row else None,
                "status": row.get("intelligibility_status", "DEVELOPMENT_PRELIMINARY")
                if row else "WAITING_FOR_HUMAN_CALIBRATION",
                "evidence": {
                    "mean_word_probability": sum(probabilities) / len(probabilities) if probabilities else None,
                    "recognized_word_count": len(words),
                    "warning": "Recognition evidence only; ASR mismatch is not a learner error.",
                },
            },
            "completeness": {
                "score": row.get("completeness") if row else None,
                "status": completeness.get("status") if completeness else "EVIDENCE_PENDING",
                "coverage": completeness.get("coverage") if completeness else None,
                "evidence": {
                    "matched_word_count": len(completeness.get("matched_sequence", []))
                    if completeness else None,
                    "omission_count": len(completeness.get("omissions", [])) if completeness else None,
                    "insertion_count": len(completeness.get("insertions", [])) if completeness else None,
                    "warning": completeness.get("warning") if completeness else None,
                },
            },
            "prosody": {
                "score": row.get("prosody") if row else None,
                "status": row.get("prosody_status", "DEVELOPMENT_PRELIMINARY_SEPARATE")
                if row else "WAITING_FOR_HUMAN_CALIBRATION",
                "evidence": {key: acoustic.get(key) for key in
                             ("f0_range_semitones", "f0_std_semitones",
                              "intensity_std_db", "voiced_fraction")},
            },
        },
        "generation": {
            "status": "NOT_YET_GENERATED",
            "strengths": [],
            "priority_improvement": None,
            "next_practice_action": None,
        },
        "safety_rules": list(SAFETY_RULES),
        "labels": DISCLAIMER,
        "holdout_processed": False,
    }
    validate_feedback_contract(payload)
    return payload


def validate_feedback_contract(payload: dict) -> None:
    if payload.get("version") != VERSION:
        raise ValueError("Unexpected feedback contract version")
    if set(payload.get("criteria", {})) != set(CRITERIA):
        raise ValueError("Feedback contract must contain exactly the five controlled-reading criteria")
    if payload.get("labels") != DISCLAIMER or payload.get("holdout_processed") is not False:
        raise ValueError("Feedback contract lacks required safety labels or holdout exclusion")
    if payload.get("generation", {}).get("status") != "NOT_YET_GENERATED":
        raise ValueError("This preparation contract cannot contain generated feedback")
    pronunciation = payload["criteria"]["pronunciation"]
    if pronunciation.get("evidence", {}).get("error_diagnoses_confirmed") is not False:
        raise ValueError("Unmeasured pronunciation errors are prohibited")
    waiting = payload.get("status") == "WAITING_FOR_HUMAN_CALIBRATION"
    if waiting and any(payload["criteria"][name].get("score") is not None for name in CRITERIA):
        raise ValueError("Uncalibrated feedback contract cannot contain numeric scores")
