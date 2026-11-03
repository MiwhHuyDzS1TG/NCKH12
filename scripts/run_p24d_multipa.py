from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from speaking_evidence.p24d_multipa import (
    RATED_IDS,
    aggregate_video,
    apply_fitted_mapping,
    calibrate_direct,
    direct_metrics,
    prepare_manifest,
    selection_decision,
    sha256_file,
    verify_frozen_inputs,
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def paths(root: Path) -> dict[str, Path]:
    local = root / ".local/multipa"
    return {
        "plan": root / "p24d_multipa_plan_v1.json",
        "local": local,
        "manifest": local / "run/segmentation_manifest.json",
        "request": local / "run/worker_request.json",
        "raw": local / "run/raw_multipa_outputs.json",
        "summary": local / "run/p24d_summary.json",
        "demo_cache": local / "demo_cache",
        "python": local / "venv/Scripts/python.exe",
        "source": local / "source",
        "hubert": local / "models/hubert_base_ls960.pt",
        "roberta": local / "models/roberta.base",
        "checkpoint": local / "models/model_assessment_val9_r1/model_assessment_val9_r1/PRO/best",
        "whisper_cache": local / "whisper_cache",
    }


def prepare(root: Path) -> dict:
    p = paths(root)
    manifest = prepare_manifest(root, p["plan"], p["local"] / "run")
    write_json(p["manifest"], manifest)
    request = {
        "mode": "PRETRAINED_INFERENCE_ONLY",
        "plan_sha256": sha256_file(p["plan"]),
        "items": manifest["items"],
        "neural_training_or_finetuning": False,
        "holdout_processed": False,
    }
    write_json(p["request"], request)
    return manifest


def infer(root: Path) -> None:
    p = paths(root)
    required = (p["python"], p["source"], p["hubert"], p["roberta"], p["checkpoint"])
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing isolated MultiPA dependency: {missing}")
    frozen_plan = json.loads(p["plan"].read_text(encoding="utf-8"))
    expected_checkpoint = frozen_plan["candidate"]["extracted_checkpoint_sha256"]
    if sha256_file(p["checkpoint"]) != expected_checkpoint:
        raise ValueError("Released MultiPA checkpoint hash does not match frozen plan")
    source_commit = subprocess.check_output(
        ["git", "-C", str(p["source"]), "rev-parse", "HEAD"], text=True).strip()
    if source_commit != frozen_plan["candidate"]["github_commit"]:
        raise ValueError("MultiPA source revision does not match frozen plan")
    if not p["request"].exists():
        prepare(root)
    command = [
        str(p["python"]), str(root / "scripts/p24d_multipa_worker.py"),
        "--request", str(p["request"]), "--output", str(p["raw"]),
        "--source", str(p["source"]), "--hubert", str(p["hubert"]),
        "--roberta", str(p["roberta"]), "--checkpoint", str(p["checkpoint"]),
        "--whisper-cache", str(p["whisper_cache"]),
    ]
    subprocess.run(command, cwd=root, check=True)


def summarize(root: Path) -> dict:
    p = paths(root)
    ratings, _, _ = verify_frozen_inputs(root, p["plan"])
    manifest = json.loads(p["manifest"].read_text(encoding="utf-8"))
    raw = json.loads(p["raw"].read_text(encoding="utf-8"))
    raw_by_pair: dict[str, list[dict]] = {pair_id: [] for pair_id in RATED_IDS}
    for row in raw["items"]:
        raw_by_pair[row["pair_id"]].append(row)
    rating_by_pair = {row["pair_id"]: row for row in ratings["items"]}
    manifest_by_pair = {row["pair_id"]: row for row in manifest["items"]}
    rows = []
    for pair_id in RATED_IDS:
        aggregate = aggregate_video(raw_by_pair[pair_id], len(manifest_by_pair[pair_id]["chunks"]))
        scores = aggregate["raw_pretrained_score"] or {}
        rating = rating_by_pair[pair_id]
        rows.append({
            "pair_id": pair_id,
            "valid": aggregate["valid"],
            "runtime_sec": aggregate["runtime_sec"],
            "teacher_fluency": rating["fluency"],
            "teacher_pronunciation": rating["pronunciation"],
            "teacher_prosody": rating["prosody"],
            "teacher_intelligibility_context_only": rating["intelligibility"],
            "multipa_accuracy": scores.get("accuracy"),
            "multipa_fluency": scores.get("fluency"),
            "multipa_prosody": scores.get("prosody"),
            "multipa_total_context_only": scores.get("total"),
            "chunk_summary": aggregate,
        })
    criteria = {
        "pronunciation": ("teacher_pronunciation", "multipa_accuracy", "pronunciation"),
        "fluency": ("teacher_fluency", "multipa_fluency", "fluency"),
        "prosody": ("teacher_prosody", "multipa_prosody", "prosody"),
    }
    tournament = json.loads((root / "assessment_runs/T001_p24_tournament_v1/criterion_tournament_summary.json").read_text(encoding="utf-8"))
    baseline_ids = {"pronunciation": "P0_ASR_RECOGNITION", "fluency": "F0_BASELINE", "prosody": "R0_PRAAT"}
    evaluation = {}
    selections = {}
    for criterion, (human, machine, label) in criteria.items():
        metric = direct_metrics(rows, human, machine)
        calibration = calibrate_direct(rows, human, machine)
        baseline = tournament["mappings"][criterion][baseline_ids[criterion]]
        decision = selection_decision(
            baseline, calibration, metric["n"], metric["raw_standard_deviation"] or 0.0,
            multi_level=(criterion == "prosody"))
        evaluation[criterion] = {"raw_pretrained": metric, "calibrated": calibration,
                                 "current_baseline": baseline, "decision": decision}
        selections[criterion] = ("MULTIPA_DIRECT_PRETRAINED" if decision["promote"]
                                 else baseline_ids[criterion])
    summary = {
        "version": "P2.4D-MultiPA-summary-v1",
        "status": "DIRECT_PRETRAINED_SCORER_FROZEN",
        "plan_sha256": sha256_file(p["plan"]),
        "environment": {
            "isolated_python": str(p["python"]),
            "host_python_unchanged": platform.python_version(),
            "device": raw.get("device"),
            "github_commit": "a8d83ec1d80f9db60e6d32227cb1c562ee5e6022",
            "huggingface_revision": "ff1e3c79bfb1d113d887a0b7b05fe2900c095264",
            "checkpoint_sha256": sha256_file(p["checkpoint"]),
        },
        "valid_videos": sum(row["valid"] for row in rows),
        "failure_rate": 1.0 - sum(row["valid"] for row in rows) / len(rows),
        "runtime_sec": sum(row["runtime_sec"] for row in rows) + raw.get("model_load_runtime_sec", 0.0),
        "rows": rows,
        "evaluation": evaluation,
        "criterion_winners": {
            **selections,
            "completeness": "NCKH12_DETERMINISTIC_ASR_ASSISTED",
            "intelligibility": "HUMAN_ONLY_MACHINE_UNSTABLE",
            "overall": None,
        },
        "fallback_oollim_used": False,
        "reserved_validation_ids": ["T001-D064", "T001-D043", "T001-D048"],
        "reserved_validation_ratings_read": False,
        "original_ratings_sha256_after": sha256_file(root / "human_ground_truth/p22a_v1/ratings_v2.json"),
        "p24_winner_freeze_sha256_after": sha256_file(root / "assessment_runs/T001_p24_tournament_v1/winner_freeze_v1.json"),
        "holdout_processed": False,
        "overall_score_created": False,
        "limitations": "N=12 development-only restricted-range labels; preliminary competition scorer, not external validation.",
    }
    write_json(p["summary"], summary)
    for pair_id in RATED_IDS[:4]:
        row = next(item for item in rows if item["pair_id"] == pair_id)
        if not row["valid"]:
            continue
        cache = {
            "version": "P2.4D-genuine-demo-cache-v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "pair_id": pair_id,
            "input_hash": manifest_by_pair[pair_id]["raw_audio_sha256"],
            "chunk_input_hashes": [chunk["wav_sha256"] for chunk in manifest_by_pair[pair_id]["chunks"]],
            "model": "MultiPA released pretrained assessment checkpoint",
            "model_sha256": summary["environment"]["checkpoint_sha256"],
            "plan_sha256": summary["plan_sha256"],
            "raw_score_label": "RAW_PRETRAINED_SCORE",
            "raw_pretrained_scores": {
                "accuracy": row["multipa_accuracy"],
                "fluency": row["multipa_fluency"],
                "prosody": row["multipa_prosody"],
                "total_context_only": row["multipa_total_context_only"],
            },
            "calibrated_score_label": "NCKH12_CALIBRATED_SCORE",
            "calibrated_scores": {
                "pronunciation": apply_fitted_mapping(
                    evaluation["pronunciation"]["calibrated"], "multipa_accuracy", row["multipa_accuracy"]),
                "fluency": None,
                "prosody": apply_fitted_mapping(
                    evaluation["prosody"]["calibrated"], "multipa_prosody", row["multipa_prosody"]),
            },
            "criterion_winners": summary["criterion_winners"],
            "genuine_inference": True,
            "fake_or_placeholder_score": False,
            "holdout": False,
            "overall_score": None,
        }
        write_json(p["demo_cache"] / f"{pair_id}.json", cache)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "infer", "summarize", "all"), nargs="?", default="all")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    started = time.perf_counter()
    if args.action in ("prepare", "all"):
        manifest = prepare(root)
        print(f"Prepared {len(manifest['items'])} development videos")
    if args.action in ("infer", "all"):
        infer(root)
    if args.action in ("summarize", "all"):
        summary = summarize(root)
        print(json.dumps({"valid_videos": summary["valid_videos"],
                          "winners": summary["criterion_winners"]}, indent=2))
    print(f"Elapsed: {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
