from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT_FROM_SCRIPT = Path(__file__).resolve().parents[1]
if str(ROOT_FROM_SCRIPT) not in sys.path:
    sys.path.insert(0, str(ROOT_FROM_SCRIPT))

from speaking_evidence.p24d_multipa import sha256_file
from speaking_evidence.p25 import (
    VALIDATION_IDS,
    create_frozen_predictions,
    evaluate_frozen_predictions,
    prepare_machine_request,
)


def paths(root: Path) -> dict[str, Path]:
    multipa = root / ".local/multipa"
    local = multipa / "p25/run"
    return {
        "local": local,
        "request": local / "worker_request.json",
        "raw": local / "raw_multipa_outputs.json",
        "predictions": local / "frozen_predictions.json",
        "evaluation": local / "p25_evaluation.json",
        "python": multipa / "venv/Scripts/python.exe",
        "source": multipa / "source",
        "hubert": multipa / "models/hubert_base_ls960.pt",
        "roberta": multipa / "models/roberta.base",
        "checkpoint": multipa / "models/model_assessment_val9_r1/model_assessment_val9_r1/PRO/best",
        "whisper_cache": multipa / "whisper_cache",
    }


def infer(root: Path) -> None:
    p = paths(root)
    required = (p["python"], p["source"], p["hubert"], p["roberta"], p["checkpoint"], p["request"])
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing frozen MultiPA input/environment: {missing}")
    plan = json.loads((root / "p25_frozen_mini_validation_plan_v1.json").read_text(encoding="utf-8"))
    if sha256_file(p["checkpoint"]) != plan["multipa"]["checkpoint_sha256"]:
        raise ValueError("Released MultiPA checkpoint changed")
    source_commit = subprocess.check_output(
        ["git", "-C", str(p["source"]), "rev-parse", "HEAD"], text=True).strip()
    if source_commit != "a8d83ec1d80f9db60e6d32227cb1c562ee5e6022":
        raise ValueError("MultiPA source revision changed")
    command = [
        str(p["python"]), str(root / "scripts/p24d_multipa_worker.py"),
        "--request", str(p["request"]), "--output", str(p["raw"]),
        "--source", str(p["source"]), "--hubert", str(p["hubert"]),
        "--roberta", str(p["roberta"]), "--checkpoint", str(p["checkpoint"]),
        "--whisper-cache", str(p["whisper_cache"]),
    ]
    subprocess.run(command, cwd=root, check=True)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def write_report(root: Path, evaluation: dict) -> None:
    lines = [
        "# P2.5 Frozen Development Mini-Validation Report", "",
        "## Scope and leakage guard", "",
        "This is a one-time, out-of-sample **development** mini-validation on `D064`, `D043`, and `D048`. "
        "The P2.4D scorer and its one-dimensional mappings were frozen before these ratings existed. "
        "Machine inputs and predictions were created in a stage that did not open the validation rating artifact; "
        "the three teacher ratings were read only by the final evaluation stage.", "",
        "No retraining, recalibration, threshold change, feature change, model reselection, Intelligibility machine "
        "score, Overall score or holdout access occurred.", "",
        "## Per-item results (primary evidence)", "",
        "| Video | Criterion | Teacher | Machine | Absolute Error |",
        "|---|---|---:|---:|---:|",
    ]
    for row in evaluation["rows"]:
        short_id = row["pair_id"].replace("T001-", "")
        for criterion in ("pronunciation", "fluency", "prosody"):
            lines.append(
                f"| {short_id} | {criterion.title()} | {row[f'teacher_{criterion}']} | "
                f"{row[f'machine_{criterion}']:.4f} | {row[f'absolute_error_{criterion}']:.4f} |"
            )
    lines.extend(["", "## Aggregate metrics", "",
                  "Correlations below are descriptive only. With N=3, they do not support significance or stable inference.", "",
                  "| Criterion | Mini MAE | Exact band | Within one band | Pearson | Spearman | Dev LOOCV MAE | Signal | Recommendation |",
                  "|---|---:|---:|---:|---:|---:|---:|---|---|"])
    for criterion in ("pronunciation", "fluency", "prosody"):
        metric = evaluation["metrics"][criterion]
        interpretation = evaluation["interpretations"][criterion]
        lines.append(
            f"| {criterion.title()} | {metric['mae']:.4f} | {metric['exact_band_accuracy']:.4f} | "
            f"{metric['within_one_band_accuracy']:.4f} | {_fmt(metric['pearson_descriptive_only'])} | "
            f"{_fmt(metric['spearman_descriptive_only'])} | {interpretation['development_loo_mae']:.4f} | "
            f"{interpretation['signal']} | {interpretation['competition_recommendation']} |"
        )
    lines.extend(["", "## Deterministic completeness and reference-only Intelligibility", "",
                  "| Video | Coverage | Score 1–5 | Matched | Omissions | Insertions | Teacher Intelligibility (reference only) |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    for row in evaluation["rows"]:
        complete = row["completeness"]
        lines.append(
            f"| {row['pair_id'].replace('T001-', '')} | {complete['coverage']:.4f} | "
            f"{complete['criterion_score_1_5']:.4f} | {complete['matched']} | "
            f"{complete['omissions']} | {complete['insertions']} | "
            f"{row['teacher_intelligibility_reference_only']} |"
        )
    lines.extend(["", "Completeness remains `ASR-assisted Reading Completeness`; ASR differences are not proven learner errors. "
                  "Intelligibility remains `HUMAN_ONLY / MACHINE_UNSTABLE`.", "",
                  "## Raw MultiPA outputs", "",
                  "| Video | Accuracy | Fluency | Prosody | Total |",
                  "|---|---:|---:|---:|---:|"])
    for row in evaluation["rows"]:
        raw = row["raw_multipa"]
        lines.append(f"| {row['pair_id'].replace('T001-', '')} | {raw['accuracy']:.4f} | "
                     f"{raw['fluency']:.4f} | {raw['prosody']:.4f} | {raw['total']:.4f} |")
    lines.extend(["", "## Competition decision", ""])
    for criterion in ("pronunciation", "fluency", "prosody"):
        result = evaluation["interpretations"][criterion]
        lines.append(f"- **{criterion.title()}:** `{result['competition_recommendation']}` — "
                     f"`{result['signal']}`.")
    lines.extend([
        "- **Completeness:** `KEEP`.",
        "- **Intelligibility:** `HUMAN_ONLY / MACHINE_UNSTABLE`.",
        "- **Overall:** not created.", "",
        "These three development cases are extremely small and AI-assisted single-rater labels. "
        "The result is a competition-engineering signal, not external validation, CEFR/B2/IELTS evidence, "
        "or permission to tune on the three cases.", "",
        "## Provenance", "",
        f"- Frozen evaluation plan SHA-256: `{evaluation['plan_sha256']}`.",
        f"- Frozen prediction artifact SHA-256: `{evaluation['frozen_predictions_sha256']}`.",
        f"- Validation rating artifact SHA-256: `{evaluation['validation_ratings_sha256']}`.",
        "- Fixed holdout processed: **NO**.",
    ])
    (root / "P25_FROZEN_MINI_VALIDATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "infer", "score", "evaluate", "report", "all"),
                        nargs="?", default="all")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    p = paths(root)
    if args.action in ("prepare", "all"):
        request = prepare_machine_request(root, p["local"])
        print(f"Prepared frozen machine inputs: {len(request['items'])}")
    if args.action in ("infer", "all"):
        infer(root)
    if args.action in ("score", "all"):
        predictions = create_frozen_predictions(root, p["local"])
        print(f"Created frozen predictions: {len(predictions['predictions'])}")
    evaluation = None
    if args.action in ("evaluate", "all"):
        evaluation = evaluate_frozen_predictions(root, p["local"])
        print(json.dumps(evaluation["metrics"], indent=2))
    if args.action in ("report", "all"):
        evaluation = evaluation or json.loads(p["evaluation"].read_text(encoding="utf-8"))
        write_report(root, evaluation)
        print("Wrote P25_FROZEN_MINI_VALIDATION_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
