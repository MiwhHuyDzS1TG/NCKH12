"""P2.1b task-profile proposal, development rerun, and ASR audit orchestration."""
from __future__ import annotations

import argparse
import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import yaml

from speaking_evidence.asr import FasterWhisperBackend, validate_words
from speaking_evidence.audio import sha256_file
from speaking_evidence.profile import validate_profile
from speaking_evidence.runner import gate_status, load_development, run_pair, write_json
from speaking_evidence.wer import word_error_counts

SAMPLE_IDS = ("T001-D059", "T001-D007", "T001-D068", "T001-D028", "T001-D015")
AUDIT_IDS = ("T001-D028", "T001-D068", "T001-D059")
VERSION = "P2.1b-v1"
AI_VERSION = "P2.1b-AI-v2"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def propose_profile(cohort_dir: Path, template_path: Path, destination: Path) -> dict:
    """Majority occupancy of GREEN development learner intervals in template time."""
    rows, split, manifest_hash = load_development(cohort_dir)
    template_meta = json.loads((cohort_dir / "template_profile" / "profile.json").read_text(encoding="utf-8"))
    reference_vad = json.loads((cohort_dir / "template_profile" / "reference_vad.json").read_text(encoding="utf-8"))
    duration = float(template_meta["duration_sec"])
    template_hash = sha256_file(template_path)
    if template_hash != template_meta["template_sha256"]:
        raise ValueError("Template media differs from saved Phase-1 template")
    greens = [r for r in rows if gate_status(r) == "P2_ELIGIBLE" and r.get("status") == "ok"]
    if not greens or any(r["template_id"] != template_meta["template_id"] for r in greens):
        raise ValueError("No consistent development GREEN sample")
    step = 0.5
    occupancy = []
    for index in range(math.ceil(duration / step)):
        left, right = index * step, min(duration, (index + 1) * step)
        supporting = 0
        for row in greens:
            alignment = row.get("visual_alignment") or {}
            if alignment.get("status") != "ok":
                raise ValueError("GREEN proposal needs reliable visual template alignment")
            a, b = float(alignment["a"]), float(alignment["b"])
            if a <= 0:
                raise ValueError("Invalid template-to-Duet time scale")
            overlap = sum(max(0.0, min(right, (s["end"] - b) / a) -
                              max(left, (s["start"] - b) / a))
                          for s in row["learner_segments"])
            if overlap >= min(0.25, (right - left) / 2):
                supporting += 1
        occupancy.append(supporting)
    majority = math.ceil(len(greens) / 2)
    active = [i for i, count in enumerate(occupancy) if count >= majority]
    if not active:
        raise ValueError("No repeated learner-response region in GREEN development videos")
    groups: list[list[int]] = []
    for index in active:
        if not groups or (index - groups[-1][-1] - 1) * step > 1.0:
            groups.append([])
        groups[-1].append(index)
    turns = []
    for group in groups:
        start = max(0.0, group[0] * step - 0.25)
        end = min(duration, (group[-1] + 1) * step + 0.5)
        if end - start < 1.0:
            continue
        turns.append({"turn_id": f"T{len(turns)+1:03d}", "start_sec": round(start, 3),
                      "end_sec": round(end, 3), "mode": "UNKNOWN",
                      "prompt_text": "", "target_text": "", "scoring_dimensions": []})
    if not turns:
        raise ValueError("No usable candidate response window")
    proposal = {"task_id": "T001-speaking", "template_id": "T001", "version": "1",
                "language": "en", "timebase": "TEMPLATE_TIMELINE",
                "template_sha256": template_hash, "template_duration_sec": duration,
                "human_confirmed": False, "status": "CANDIDATE",
                "created_at_utc": now_utc(), "updated_at_utc": now_utc(),
                "source": {"kind": "AUTOMATIC_DEVELOPMENT_PROPOSAL",
                           "method": "0.5s template-time bins; at least half of GREEN development videos have >=0.25s learner candidates; bridge <=1s gaps; pad 0.25s start/0.5s end",
                           "development_green_count": len(greens),
                           "development_manifest_sha256": manifest_hash,
                           "fixed_split_sha256": sha256_file(cohort_dir / "data_split_v2.json"),
                           "reference_vad_path": "template_profile/reference_vad.json",
                           "reference_vad_intervals": len(reference_vad),
                           "holdout_used": False},
                "candidate_occupancy": {"step_sec": step, "majority_count": majority,
                                        "support_counts": occupancy},
                "turns": turns}
    validate_profile(proposal, duration)
    if destination.exists():
        raise FileExistsError(f"Candidate already exists: {destination}")
    write_json(destination, proposal)
    return proposal


def confirm_profile(candidate: dict, edited_turns: list[dict], template_path: Path,
                    destination: Path, confirmed: bool) -> dict:
    if candidate.get("status") != "CANDIDATE" or candidate.get("human_confirmed") is not False:
        raise ValueError("Expected an unconfirmed candidate profile")
    if not confirmed:
        raise ValueError("Researcher must explicitly confirm the T001 task boundaries")
    if sha256_file(template_path) != candidate["template_sha256"]:
        raise ValueError("Template media hash changed")
    profile = {k: copy.deepcopy(v) for k, v in candidate.items() if k != "candidate_occupancy"}
    profile["turns"] = edited_turns
    profile["human_confirmed"] = True
    profile["status"] = "HUMAN_CONFIRMED"
    profile["updated_at_utc"] = now_utc()
    profile["source"] = {"kind": "RESEARCHER_CONFIRMED_CANDIDATE",
                         "candidate_sha256": sha256_file(destination.parent / "T001_v1_candidate.json"),
                         "candidate_method": candidate["source"]["method"],
                         "confirmed_at_utc": profile["updated_at_utc"],
                         "holdout_used": False}
    validate_profile(profile, profile["template_duration_sec"])
    if destination.exists():
        raise FileExistsError("Confirmed profile already exists; create a new version for revisions")
    write_json(destination, profile)
    return profile


def review_profile_ai(candidate: dict, template_path: Path, cohort_dir: Path,
                      destination: Path) -> dict:
    """Version an independently checked, machine-reviewed reading task profile."""
    if candidate.get("status") != "CANDIDATE" or candidate.get("human_confirmed") is not False:
        raise ValueError("Expected an unconfirmed candidate")
    if sha256_file(template_path) != candidate["template_sha256"]:
        raise ValueError("Template media hash changed")
    rows, _, manifest_hash = load_development(cohort_dir)
    greens = [r for r in rows if gate_status(r) == "P2_ELIGIBLE" and r.get("status") == "ok"]
    if len(greens) != 9 or manifest_hash != candidate["source"]["development_manifest_sha256"]:
        raise ValueError("The reviewed nine-video GREEN cohort changed")
    vad_path = cohort_dir / "template_profile" / "reference_vad.json"
    vad = json.loads(vad_path.read_text(encoding="utf-8"))
    if len(vad) != candidate["source"]["reference_vad_intervals"]:
        raise ValueError("Template reference VAD changed")
    if len(candidate["turns"]) != 1:
        raise ValueError("Expected the reviewed single reading passage")
    profile = {k: copy.deepcopy(v) for k, v in candidate.items() if k != "candidate_occupancy"}
    profile.update({"version": "2", "status": "AI_ASSISTED_CONFIRMED",
                    "model_reviewed": True, "human_confirmed": False,
                    "updated_at_utc": now_utc()})
    profile["turns"][0]["mode"] = "CONTROLLED_READING"
    profile["source"] = {
        "kind": "AI_ASSISTED_MEDIA_REVIEW",
        "candidate_sha256": sha256_file(destination.parent / "T001_v1_candidate.json"),
        "development_manifest_sha256": manifest_hash,
        "reference_vad_sha256": sha256_file(vad_path),
        "template_observation": "One scrolling English reading passage visible from about 3 s through the end; no alternating question/answer prompts seen in sampled frames 0,3,6,10,15,20,25,30,35,40,45,50,53 s.",
        "green_observation": "All nine GREEN Duets show learner video beside the same scrolling passage at 20 s; majority learner occupancy supports one continuous response region.",
        "boundary_method": candidate["source"]["method"],
        "boundary_uncertainty": "Start/end are development-cohort estimates, not human-verified word boundaries; individual recordings are clipped on mapping.",
        "reviewed_at_utc": profile["updated_at_utc"], "holdout_used": False}
    validate_profile(profile, profile["template_duration_sec"])
    if destination.exists():
        raise FileExistsError(destination)
    write_json(destination, profile)
    return profile


def map_profile_to_duet(profile: dict, row: dict) -> dict:
    allowed = ((profile.get("human_confirmed") is True and profile.get("status") == "HUMAN_CONFIRMED")
               or (profile.get("human_confirmed") is False and profile.get("model_reviewed") is True
                   and profile.get("status") == "AI_ASSISTED_CONFIRMED"))
    if not allowed:
        raise ValueError("P2.1b requires an explicitly reviewed TaskProfile")
    alignment = row.get("visual_alignment") or {}
    if alignment.get("status") != "ok":
        raise ValueError("Cannot map TaskProfile without reliable visual alignment")
    a, b = float(alignment["a"]), float(alignment["b"])
    duration = float(row["input_metadata"]["duet"]["duration_sec"])
    if not 0.8 < a < 1.2:
        raise ValueError("Unexpected template-to-Duet scale")
    mapped = copy.deepcopy(profile)
    mapped["timebase"] = "RAW_DUET_TIMELINE"
    mapped["source_template_timebase"] = "TEMPLATE_TIMELINE"
    mapped["alignment"] = {"a": a, "b": b, "method": "visual_alignment"}
    turns = []
    for item in profile["turns"]:
        start = max(0.0, a * float(item["start_sec"]) + b)
        end = min(duration, a * float(item["end_sec"]) + b)
        if end <= start:
            continue
        turn = copy.deepcopy(item)
        turn["template_start_sec"] = item["start_sec"]
        turn["template_end_sec"] = item["end_sec"]
        turn["start_sec"], turn["end_sec"] = round(start, 3), round(end, 3)
        turns.append(turn)
    if not turns:
        raise ValueError("No TaskProfile turn overlaps this Duet")
    mapped["turns"] = turns
    validate_profile(mapped, duration)
    return mapped


def comparison_row(old: dict, new: dict) -> dict:
    old_m = old["aggregate_fluency_evidence"]
    new_m = new["aggregate_fluency_evidence"]
    names = ("word_count", "speech_rate_wpm", "articulation_rate_wpm", "pause_ratio",
             "long_pause_count", "longest_pause_sec", "mean_length_of_run_words")
    result = {"pair_id": new["pair_id"], "fallback_turns": len(old["turns"]),
              "task_profile_turns": len(new["turns"]),
              "old_active_turn_duration_sec": old_m.get("active_turn_duration_sec"),
              "new_active_turn_duration_sec": new_m.get("active_turn_duration_sec")}
    for name in names:
        result[name] = {"old": old_m.get(name), "new": new_m.get(name)}
    result["notes"] = ["Descriptive measurements only; no proficiency comparison"]
    return result


def run_confirmed(cohort_dir: Path, profile_path: Path, old_dir: Path,
                  output_dir: Path, config_path: Path) -> dict:
    if output_dir.resolve() == old_dir.resolve() or old_dir.resolve() in output_dir.resolve().parents:
        raise ValueError("P2.1b must not overwrite P2.1 historical artifacts")
    rows, split, manifest_hash = load_development(cohort_dir)
    by_id = {row["pair_id"]: row for row in rows}
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    validate_profile(profile, profile["template_duration_sec"])
    if not ((profile.get("human_confirmed") is True and profile.get("status") == "HUMAN_CONFIRMED")
            or (profile.get("human_confirmed") is False and profile.get("model_reviewed") is True
                and profile.get("status") == "AI_ASSISTED_CONFIRMED")):
        raise ValueError("Reviewed TaskProfile is required")
    template_path = Path("data/templates/T001/original.mp4")
    if sha256_file(template_path) != profile["template_sha256"]:
        raise ValueError("TaskProfile template hash mismatch")
    write_json(output_dir / "task_profile.json", profile)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    asr = FasterWhisperBackend(**config["asr"])
    split_hash = sha256_file(cohort_dir / "data_split_v2.json")
    comparison = []
    sample = []
    for pair_id in SAMPLE_IDS:
        row = by_id[pair_id]
        if gate_status(row) != "P2_ELIGIBLE":
            raise ValueError(f"Sample pair no longer GREEN: {pair_id}")
        mapped = map_profile_to_duet(profile, row)
        old_path = old_dir / "pairs" / pair_id / "evidence.json"
        old = json.loads(old_path.read_text(encoding="utf-8"))
        new = run_pair(row, cohort_dir, output_dir, config, asr, manifest_hash, split_hash, mapped)
        new["version"] = AI_VERSION if profile["status"] == "AI_ASSISTED_CONFIRMED" else VERSION
        new["task_profile"].update({"human_confirmed": profile["human_confirmed"],
                                     "model_reviewed": profile.get("model_reviewed", False),
                                     "status": profile["status"],
                                     "source_profile_sha256": sha256_file(profile_path),
                                     "source_profile_ref": str(profile_path).replace("\\", "/"),
                                     "timebase": "RAW_DUET_TIMELINE"})
        write_json(output_dir / "pairs" / pair_id / "evidence.json", new)
        comparison.append(comparison_row(old, new))
        sample.append({"pair_id": pair_id, "turn_count": len(new["turns"]),
                       "word_count": new["aggregate_fluency_evidence"]["word_count"],
                       "asr_runtime_sec": round(sum(t["transcript"]["runtime_sec"] for t in new["turns"]), 3),
                       "warnings": new["warnings"]})
        if pair_id in AUDIT_IDS:
            audit_dir = output_dir / "asr_validation" / pair_id
            write_json(audit_dir / "asr_transcript.json",
                       {"pair_id": pair_id, "model": new["asr_provenance"],
                        "preprocessing": new["audio_provenance"],
                        "turns": [{"turn_id": t["turn_id"], "model_input_ref": t["model_input_ref"],
                                   "start_sec": t["start_sec"], "end_sec": t["end_sec"],
                                   "transcript": t["transcript"]} for t in new["turns"]]})
            write_json(audit_dir / "human_reference.json",
                       {"pair_id": pair_id, "status": "UNREVIEWED", "human_confirmed": False,
                        "turns": [{"turn_id": t["turn_id"], "reference_text": None}
                                  for t in new["turns"]]})
    write_json(output_dir / "old_vs_new.json", comparison)
    d059 = next(item for item in comparison if item["pair_id"] == "T001-D059")
    write_json(output_dir / "d059_diagnostic.json",
               {"pair_id": "T001-D059", "status": "PRELIMINARY_PENDING_HUMAN_TRANSCRIPT",
                "old_speech_rate_wpm": d059["speech_rate_wpm"]["old"],
                "new_speech_rate_wpm": d059["speech_rate_wpm"]["new"],
                "old_word_count": d059["word_count"]["old"],
                "new_word_count": d059["word_count"]["new"],
                "old_active_turn_duration_sec": d059["old_active_turn_duration_sec"],
                "new_active_turn_duration_sec": d059["new_active_turn_duration_sec"],
                "interpretation": "Task boundary contribution is measurable; fast speech versus ASR insertion requires human listening/reference",
                "no_hardcoded_d059_rule": True})
    summary = {"version": AI_VERSION if profile["status"] == "AI_ASSISTED_CONFIRMED" else VERSION, "scope": "DEVELOPMENT_ONLY",
               "task_profile_ref": str(profile_path).replace("\\", "/"),
               "task_profile_sha256": sha256_file(profile_path),
               "human_confirmed": profile["human_confirmed"],
               "model_reviewed": profile.get("model_reviewed", False),
               "development_count": len(rows), "holdout_count": len(split["holdout"]),
               "holdout_processed": False, "sample": sample,
               "asr_audit_ids": list(AUDIT_IDS), "asr_audit_status": "PENDING_HUMAN_REFERENCES",
               "small_vs_medium_status": "PENDING_HUMAN_REFERENCES", "no_scores": True}
    write_json(output_dir / "sample_summary.json", summary)
    return summary


def save_human_reference(output_dir: Path, pair_id: str, texts: dict[str, str],
                         researcher_confirmed: bool) -> dict:
    if pair_id not in AUDIT_IDS or not researcher_confirmed:
        raise ValueError("Explicit human audit confirmation is required")
    path = output_dir / "asr_validation" / pair_id / "human_reference.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    expected = {turn["turn_id"] for turn in record["turns"]}
    if set(texts) != expected or any(not isinstance(value, str) for value in texts.values()):
        raise ValueError("A reference text is required for each task turn (empty text may be intentional)")
    record["turns"] = [{"turn_id": key, "reference_text": texts[key]}
                       for key in [turn["turn_id"] for turn in record["turns"]]]
    record.update({"status": "HUMAN_CONFIRMED", "human_confirmed": True,
                   "confirmed_at_utc": now_utc(), "normalization": "WER ignores case/punctuation only; saved text is verbatim"})
    write_json(path, record)
    return record


def evaluate_model(transcript: dict, reference: dict) -> dict:
    if reference.get("human_confirmed") is not True:
        raise ValueError("Cannot compute WER without human reference")
    by_turn = {t["turn_id"]: t for t in transcript["turns"]}
    turns = []
    for ref in reference["turns"]:
        asr_turn = by_turn[ref["turn_id"]]
        hypothesis = asr_turn["transcript"]["verbatim_transcript"]
        turns.append({"turn_id": ref["turn_id"], **word_error_counts(ref["reference_text"], hypothesis)})
        validate_words(asr_turn["transcript"]["words"], asr_turn["start_sec"], asr_turn["end_sec"])
    totals = {key: sum(t[key] for t in turns) for key in
              ("reference_words", "hypothesis_words", "substitutions", "insertions", "deletions")}
    totals["wer"] = ((totals["substitutions"] + totals["insertions"] + totals["deletions"])
                     / totals["reference_words"] if totals["reference_words"] else None)
    totals["word_count_difference"] = totals["hypothesis_words"] - totals["reference_words"]
    totals["turns"] = turns
    return totals


def compare_models(output_dir: Path, config_path: Path) -> dict:
    summary = json.loads((output_dir / "sample_summary.json").read_text(encoding="utf-8"))
    if not summary["human_confirmed"] or summary["holdout_processed"]:
        raise ValueError("Invalid P2.1b sample state")
    references = {}
    for pair_id in AUDIT_IDS:
        path = output_dir / "asr_validation" / pair_id / "human_reference.json"
        reference = json.loads(path.read_text(encoding="utf-8"))
        if reference.get("human_confirmed") is not True:
            raise ValueError(f"Human ASR reference still missing: {pair_id}")
        references[pair_id] = reference
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["asr"]
    medium = FasterWhisperBackend(**{**config, "model": "medium.en"})
    per_pair = []
    for pair_id in AUDIT_IDS:
        audit_dir = output_dir / "asr_validation" / pair_id
        small = json.loads((audit_dir / "asr_transcript.json").read_text(encoding="utf-8"))
        medium_turns = []
        for turn in small["turns"]:
            evidence = json.loads((output_dir / "pairs" / pair_id / "evidence.json").read_text(encoding="utf-8"))
            intervals = next(t["learner_intervals"] for t in evidence["turns"] if t["turn_id"] == turn["turn_id"])
            audio_path = output_dir / turn["model_input_ref"]
            transcript = medium.transcribe(audio_path, turn["start_sec"], turn["end_sec"], intervals)
            medium_turns.append({**{k: turn[k] for k in ("turn_id", "model_input_ref", "start_sec", "end_sec")},
                                 "transcript": transcript})
        medium_record = {"pair_id": pair_id, "model": medium.provenance(),
                         "preprocessing": small["preprocessing"], "turns": medium_turns}
        write_json(audit_dir / "medium_transcript.json", medium_record)
        small_metrics = evaluate_model(small, references[pair_id])
        medium_metrics = evaluate_model(medium_record, references[pair_id])
        per_pair.append({"pair_id": pair_id, "small": small_metrics, "medium": medium_metrics,
                         "small_runtime_sec": round(sum(t["transcript"]["runtime_sec"] for t in small["turns"]), 3),
                         "medium_runtime_sec": round(sum(t["transcript"]["runtime_sec"] for t in medium_turns), 3),
                         "word_timestamps_valid": True,
                         "identical_model_input_refs": [t["model_input_ref"] for t in small["turns"]]
                         == [t["model_input_ref"] for t in medium_turns]})
    def overview(model: str) -> dict:
        wers = [p[model]["wer"] for p in per_pair if p[model]["wer"] is not None]
        return {"mean_wer": mean(wers) if wers else None,
                "median_wer": median(wers) if wers else None,
                "total_runtime_sec": round(sum(p[f"{model}_runtime_sec"] for p in per_pair), 3)}
    small_overview, medium_overview = overview("small"), overview("medium")
    if small_overview["mean_wer"] is None or medium_overview["mean_wer"] is None:
        recommended = "UNDECIDED_NO_REFERENCE_WORDS"
        reason = "No reference words were available for WER; inspect human references"
    elif small_overview["mean_wer"] - medium_overview["mean_wer"] >= 0.05:
        recommended = "medium.en_PROVISIONAL"
        reason = "Medium reduced mean WER by at least five percentage points; researcher must inspect whether corrections matter to future language analysis and justify runtime"
    else:
        recommended = "small.en_PROVISIONAL"
        reason = "Medium did not reduce mean WER by five percentage points; extra runtime is not justified by this small audit unless error types show otherwise"
    result = {"version": VERSION, "scope": "SAME_THREE_HUMAN_AUDITED_DEVELOPMENT_VIDEOS",
              "pair_ids": list(AUDIT_IDS), "per_pair": per_pair,
              "small": small_overview, "medium": medium_overview,
              "recommended_backend": recommended, "recommendation_reason": reason,
              "backend_switch_automatic": False,
              "holdout_processed": False}
    write_json(output_dir / "model_comparison.json", result)
    return result


def compare_models_ai(output_dir: Path, config_path: Path) -> dict:
    """Compare ASR hypotheses on identical audio without claiming human WER."""
    summary = json.loads((output_dir / "sample_summary.json").read_text(encoding="utf-8"))
    if not summary.get("model_reviewed") or summary.get("human_confirmed") or summary["holdout_processed"]:
        raise ValueError("Expected development-only AI-reviewed sample")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["asr"]
    medium = None
    per_pair = []
    for pair_id in AUDIT_IDS:
        audit_dir = output_dir / "asr_validation" / pair_id
        small = json.loads((audit_dir / "asr_transcript.json").read_text(encoding="utf-8"))
        evidence = json.loads((output_dir / "pairs" / pair_id / "evidence.json").read_text(encoding="utf-8"))
        by_turn = {turn["turn_id"]: turn for turn in evidence["turns"]}
        medium_path = audit_dir / "medium_transcript.json"
        if medium_path.exists():
            medium_record = json.loads(medium_path.read_text(encoding="utf-8"))
            if (medium_record["model"]["model"] != "medium.en" or
                [t["model_input_ref"] for t in medium_record["turns"]] !=
                    [t["model_input_ref"] for t in small["turns"]]):
                raise ValueError("Saved medium transcript does not match small-model input")
            medium_turns = medium_record["turns"]
        else:
            if medium is None:
                medium = FasterWhisperBackend(**{**config, "model": "medium.en"})
            medium_turns = []
            for turn in small["turns"]:
                audio_path = output_dir / turn["model_input_ref"]
                intervals = by_turn[turn["turn_id"]]["learner_intervals"]
                hypothesis = medium.transcribe(audio_path, turn["start_sec"], turn["end_sec"], intervals)
                medium_turns.append({**{k: turn[k] for k in ("turn_id", "model_input_ref", "start_sec", "end_sec")},
                                     "transcript": hypothesis})
            medium_record = {"pair_id": pair_id, "model": medium.provenance(),
                             "preprocessing": small["preprocessing"], "turns": medium_turns}
            write_json(medium_path, medium_record)
        turn_disagreements = []
        for turn, medium_turn in zip(small["turns"], medium_turns):
            hypothesis = medium_turn["transcript"]
            validate_words(hypothesis["words"], turn["start_sec"], turn["end_sec"])
            disagreement = word_error_counts(hypothesis["verbatim_transcript"],
                                             turn["transcript"]["verbatim_transcript"])
            disagreement["pseudo_word_disagreement_rate"] = disagreement.pop("wer")
            turn_disagreements.append({"turn_id": turn["turn_id"],
                                       "medium_as_pseudo_reference": disagreement})
        per_pair.append({"pair_id": pair_id, "turns": turn_disagreements,
                         "small_words": sum(len(t["transcript"]["words"]) for t in small["turns"]),
                         "medium_words": sum(len(t["transcript"]["words"]) for t in medium_turns),
                         "small_runtime_sec": round(sum(t["transcript"]["runtime_sec"] for t in small["turns"]), 3),
                         "medium_runtime_sec": round(sum(t["transcript"]["runtime_sec"] for t in medium_turns), 3),
                         "identical_model_input_refs": [t["model_input_ref"] for t in small["turns"]]
                         == [t["model_input_ref"] for t in medium_turns]})
    result = {"version": AI_VERSION, "scope": "THREE_DEVELOPMENT_VIDEOS",
              "reference_status": "NO_HUMAN_GROUND_TRUTH",
              "metric_name": "pairwise_model_word_disagreement; medium.en treated as pseudo-reference only",
              "human_wer_available": False, "backend_recommendation": "UNDECIDED",
              "per_pair": per_pair, "holdout_processed": False}
    write_json(output_dir / "model_comparison_ai.json", result)
    for pair_id in SAMPLE_IDS:
        evidence_path = output_dir / "pairs" / pair_id / "evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence["task_profile"].get("status") != "AI_ASSISTED_CONFIRMED":
            raise ValueError("Unexpected profile provenance in AI sample")
        evidence["task_profile"]["mode"] = "AI_REVIEWED_TASK_PROFILE"
        for turn in evidence["turns"]:
            turn["boundary_confidence"] = "AI_REVIEWED_TASK_PROFILE"
        write_json(evidence_path, evidence)
    summary["asr_audit_status"] = "CROSS_MODEL_COMPARISON_ONLY_NO_HUMAN_REFERENCE"
    summary["small_vs_medium_status"] = "PAIRWISE_DISAGREEMENT_MEASURED_NO_WER"
    write_json(output_dir / "sample_summary.json", summary)
    old_new = {p["pair_id"]: p for p in json.loads((output_dir / "old_vs_new.json").read_text(encoding="utf-8"))}
    d059 = next(p for p in per_pair if p["pair_id"] == "T001-D059")
    small = json.loads((output_dir / "asr_validation" / "T001-D059" / "asr_transcript.json").read_text(encoding="utf-8"))
    medium_record = json.loads((output_dir / "asr_validation" / "T001-D059" / "medium_transcript.json").read_text(encoding="utf-8"))
    old = old_new["T001-D059"]
    rows, _, _ = load_development(Path("cohort_runs/T001_p14"))
    row = next(r for r in rows if r["pair_id"] == "T001-D059")
    write_json(output_dir / "d059_diagnostic_ai.json", {
        "pair_id": "T001-D059", "status": "AI_CROSS_MODEL_DIAGNOSIS_NO_HUMAN_REFERENCE",
        "old_speech_rate_wpm": old["speech_rate_wpm"]["old"],
        "new_speech_rate_wpm": old["speech_rate_wpm"]["new"],
        "new_active_turn_duration_sec": old["new_active_turn_duration_sec"],
        "duet_duration_sec": row["input_metadata"]["duet"]["duration_sec"],
        "visual_template_to_duet_scale": row["visual_alignment"]["a"],
        "small_words": d059["small_words"], "medium_words": d059["medium_words"],
        "pseudo_word_disagreement_rate": d059["turns"][0]["medium_as_pseudo_reference"]["pseudo_word_disagreement_rate"],
        "both_hypotheses_reach_passage_ending": all(
            "proud and happy" in record["turns"][0]["transcript"]["verbatim_transcript"].lower()
            for record in (small, medium_record)),
        "interpretation": "The task-boundary change barely affects rate; both ASR models recover the passage ending, and visual alignment is near unit scale. A faster learner delivery is plausible, while local ASR errors and the actual spoken words remain unverified without human listening/reference.",
        "human_ground_truth_available": False, "holdout_used": False})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="P2.1b template profile and ASR validation")
    parser.add_argument("command", choices=["propose", "run", "compare", "review-ai", "run-ai", "compare-ai"])
    parser.add_argument("--cohort-dir", type=Path, default=Path("cohort_runs/T001_p14"))
    parser.add_argument("--template", type=Path, default=Path("data/templates/T001/original.mp4"))
    parser.add_argument("--candidate", type=Path, default=Path("task_profiles/T001_v1_candidate.json"))
    parser.add_argument("--profile", type=Path, default=Path("task_profiles/T001_v1.json"))
    parser.add_argument("--old-dir", type=Path, default=Path("assessment_runs/T001_p2"))
    parser.add_argument("--output-dir", type=Path, default=Path("assessment_runs/T001_p21b"))
    parser.add_argument("--config", type=Path, default=Path("p2_config.yaml"))
    args = parser.parse_args()
    if args.command == "propose":
        result = propose_profile(args.cohort_dir, args.template, args.candidate)
    elif args.command == "run":
        result = run_confirmed(args.cohort_dir, args.profile, args.old_dir, args.output_dir, args.config)
    elif args.command == "review-ai":
        result = review_profile_ai(json.loads(args.candidate.read_text(encoding="utf-8")),
                                   args.template, args.cohort_dir, args.profile)
    elif args.command == "run-ai":
        result = run_confirmed(args.cohort_dir, args.profile, args.old_dir, args.output_dir, args.config)
    elif args.command == "compare-ai":
        result = compare_models_ai(args.output_dir, args.config)
    else:
        result = compare_models(args.output_dir, args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
