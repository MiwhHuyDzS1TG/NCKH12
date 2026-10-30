"""Development-only P2.1 runner. It does not create proficiency scores."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import yaml

from duet_segmenter.media import probe
from speaking_evidence import VERSION
from speaking_evidence.acoustic import measure_acoustic
from speaking_evidence.asr import FasterWhisperBackend
from speaking_evidence.audio import prepare_turn_audio, require_raw_source, sha256_file
from speaking_evidence.fluency import aggregate_fluency, measure_fluency
from speaking_evidence.profile import build_turns, validate_profile


def gate_status(row: dict) -> str:
    return {"GREEN": "P2_ELIGIBLE", "AMBER": "P2_REVIEW_REQUIRED",
            "RED": "P2_BLOCKED"}.get(row.get("quality_gate"), "P2_BLOCKED")


def load_development(cohort_dir: Path) -> tuple[list[dict], dict, str]:
    split_path = cohort_dir / "data_split_v2.json"
    manifest_path = cohort_dir / "development_manifest_v3.json"
    split = json.loads(split_path.read_text(encoding="utf-8"))
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    development, holdout = set(split["development"]), set(split["holdout"])
    ids = [row["pair_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != development or development & holdout:
        raise ValueError("V3 development manifest does not match the fixed V2 split")
    if len(holdout) != 18:
        raise ValueError("Expected the fixed 18-video holdout")
    return rows, split, sha256_file(manifest_path)


def representative_green(rows: list[dict], count: int) -> list[dict]:
    eligible = sorted((r for r in rows if gate_status(r) == "P2_ELIGIBLE"
                       and r.get("status") == "ok"),
                      key=lambda r: (r.get("input_metadata", {}).get("duet", {}).get("duration_sec", 0),
                                     r["pair_id"]))
    if count >= len(eligible):
        return eligible
    if count <= 0:
        return []
    indices = [round(i * (len(eligible) - 1) / (count - 1)) for i in range(count)] if count > 1 else [len(eligible)//2]
    return [eligible[i] for i in indices]


def write_json(path: Path, data: dict | list) -> None:
    import numpy as np

    def encode(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(f"Cannot serialize {type(value).__name__}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                               allow_nan=False, default=encode) + "\n", encoding="utf-8")


def run_pair(row: dict, cohort_dir: Path, output_dir: Path, config: dict,
             asr: FasterWhisperBackend, manifest_hash: str,
             split_hash: str, profile: dict | None = None) -> dict:
    if gate_status(row) != "P2_ELIGIBLE":
        raise ValueError("Phase-1 gate blocks automatic P2 evidence generation")
    pair_id = row["pair_id"]
    source = Path(row["duet_path"])
    require_raw_source(source)
    info = probe(source)
    if profile is not None:
        validate_profile(profile, info.duration_sec)
        if profile["template_id"] != row["template_id"]:
            raise ValueError("TaskProfile template does not match this pair")
    mode, turns = build_turns(row["learner_segments"], info.duration_sec,
                              config["fluency"]["turn_group_gap_sec"], profile)
    pair_root = output_dir / "pairs" / pair_id
    warnings = []
    if mode == "AUTO_TURN_FALLBACK":
        warnings.append("AUTO_TURN_FALLBACK: task boundaries are inferred from learner gaps, not human-authored")
    if not turns:
        warnings.append("NO_LEARNER_TURNS")
    source_hash = sha256_file(source)
    started = time.perf_counter()
    outcomes = []
    for turn in turns:
        turn_dir = pair_root / "turns" / turn["turn_id"]
        audio_path = turn_dir / "model_input.wav"
        audio = prepare_turn_audio(source, turn, audio_path, config["audio"]["sample_rate"])
        if turn["learner_intervals"] and len(audio) >= int(0.35 * config["audio"]["sample_rate"]):
            transcript = asr.transcribe(audio_path, turn["start_sec"], turn["end_sec"],
                                        turn["learner_intervals"])
        else:
            transcript = {"segments": [], "words": [], "verbatim_transcript": "",
                          "normalized_transcript": "", "runtime_sec": 0.0,
                          "language_probability": None}
            warnings.append(f"{turn['turn_id']}: ASR skipped because learner audio is too short or absent")
        fluency = measure_fluency(turn, transcript["words"],
                                  config["fluency"]["pause_min_sec"],
                                  config["fluency"]["long_pause_sec"])
        acoustic = measure_acoustic(audio, config["audio"]["sample_rate"],
                                    config["acoustic"]["pitch_floor_hz"],
                                    config["acoustic"]["pitch_ceiling_hz"])
        if not acoustic["available"]:
            warnings.append(f"{turn['turn_id']}: pitch unavailable ({acoustic['reason']})")
        turn_output = {**turn, "model_input_ref": str(audio_path.relative_to(output_dir)).replace("\\", "/"),
                       "transcript": transcript, "fluency": fluency, "acoustic": acoustic}
        outcomes.append(turn_output)
        write_json(turn_dir / "transcript.json", transcript)
    aggregate = aggregate_fluency(outcomes, config["fluency"]["pause_min_sec"],
                                   config["fluency"]["long_pause_sec"])
    provenance = {"canonical_source": "RAW_COMPLETED_DUET",
                  "source_ref": f"cohort_manifest_source.json#{pair_id}",
                  "source_sha256": source_hash,
                  "source_duration_sec": info.duration_sec,
                  "source_audio_sample_rate": info.audio_sample_rate,
                  "source_audio_channels": info.audio_channels,
                  "model_input_sample_rate": config["audio"]["sample_rate"],
                  "channel_conversion": "ffmpeg mono downmix",
                  "model_input_conversion": "ffmpeg PCM16 + noncandidate samples zeroed",
                  "extractor_version": VERSION}
    evidence = {"version": VERSION, "pair_id": pair_id,
                "p2_gate": "P2_ELIGIBLE", "phase1_source": {
                    "version": row.get("p14c_triage_version", "P1.4c-v3"),
                    "development_manifest_sha256": manifest_hash,
                    "fixed_split_sha256": split_hash,
                    "analysis_signature": row.get("analysis_signature")},
                "task_profile": {"mode": mode, "version": profile["version"] if profile else None,
                                 "task_id": profile["task_id"] if profile else None},
                "audio_provenance": provenance, "asr_provenance": asr.provenance(),
                "turns": outcomes, "aggregate_fluency_evidence": aggregate,
                "runtime_sec": round(time.perf_counter() - started, 3),
                "warnings": warnings,
                "limitations": ["No proficiency score is produced",
                                "ASR errors are not learner grammar or pronunciation errors",
                                "Speech rate alone is not fluency; pitch variability alone is not prosody quality",
                                "Phase-1 GREEN permits evidence extraction, not a validated speaking score"]}
    write_json(pair_root / "evidence.json", evidence)
    write_json(pair_root / "transcript.json", {"pair_id": pair_id,
              "turns": [{"turn_id": t["turn_id"], **t["transcript"]} for t in outcomes]})
    write_json(pair_root / "fluency_evidence.json", {"pair_id": pair_id,
              "turns": [{"turn_id": t["turn_id"], **t["fluency"]} for t in outcomes],
              "aggregate": aggregate})
    write_json(pair_root / "acoustic_evidence.json", {"pair_id": pair_id,
              "turns": [{"turn_id": t["turn_id"], **t["acoustic"]} for t in outcomes]})
    return evidence


def run(cohort_dir: Path, output_dir: Path, config_path: Path, sample_size: int,
        pair_ids: list[str] | None = None, profile_path: Path | None = None) -> dict:
    rows, split, manifest_hash = load_development(cohort_dir)
    by_id = {row["pair_id"]: row for row in rows}
    if pair_ids:
        if any(pair_id not in by_id for pair_id in pair_ids):
            raise ValueError("Pair ID is outside the development manifest")
        selected = [by_id[pair_id] for pair_id in pair_ids]
    else:
        selected = representative_green(rows, sample_size)
    if any(gate_status(row) != "P2_ELIGIBLE" for row in selected):
        raise ValueError("Selected AMBER/RED pair is blocked by the default Phase-1 gate")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path else None
    asr = FasterWhisperBackend(**config["asr"])
    split_hash = sha256_file(cohort_dir / "data_split_v2.json")
    sample = []
    for row in selected:
        result = run_pair(row, cohort_dir, output_dir, config, asr, manifest_hash, split_hash, profile)
        metrics = result["aggregate_fluency_evidence"]
        sample.append({"pair_id": row["pair_id"], "duration_sec": result["audio_provenance"]["source_duration_sec"],
                       "turn_count": len(result["turns"]), "asr_word_count": metrics["word_count"],
                       "asr_runtime_sec": round(sum(t["transcript"]["runtime_sec"] for t in result["turns"]), 3),
                       "speech_rate_wpm": metrics["speech_rate_wpm"],
                       "articulation_rate_wpm": metrics["articulation_rate_wpm"],
                       "pause_ratio": metrics["pause_ratio"],
                       "longest_pause_sec": metrics["longest_pause_sec"],
                       "f0_evidence_available": any(t["acoustic"]["available"] for t in result["turns"]),
                       "warnings": result["warnings"]})
    demos = {}
    for gate in ("AMBER", "RED"):
        candidate = next((r for r in rows if r.get("quality_gate") == gate), None)
        if candidate:
            demos[gate] = {"pair_id": candidate["pair_id"], "p2_gate": gate_status(candidate),
                           "processed": False}
    summary = {"version": VERSION, "scope": "DEVELOPMENT_ONLY",
               "fixed_split_sha256": split_hash, "development_manifest_sha256": manifest_hash,
               "development_count": len(rows), "holdout_count": len(split["holdout"]),
               "holdout_processed": False, "sample": sample,
               "gate_demonstrations": demos, "asr": asr.provenance(),
               "no_scores": True}
    write_json(output_dir / "cohort_summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="P2.1 development-only speaking measurements")
    parser.add_argument("--cohort-dir", type=Path, default=Path("cohort_runs/T001_p14"))
    parser.add_argument("--output-dir", type=Path, default=Path("assessment_runs/T001_p2"))
    parser.add_argument("--config", type=Path, default=Path("p2_config.yaml"))
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--pair-id", action="append", dest="pair_ids")
    parser.add_argument("--task-profile", type=Path)
    args = parser.parse_args()
    result = run(args.cohort_dir, args.output_dir, args.config, args.sample_size,
                 args.pair_ids, args.task_profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
