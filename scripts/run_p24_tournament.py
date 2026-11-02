"""Resumable P2.4 pretrained speech-model tournament."""
from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_evidence.p24 import (
    VERSION,
    _asr_selection,
    assert_split_policy,
    build_apa_pca_features,
    build_completeness_by_asr,
    build_multi_asr_features,
    build_whisperx_fluency,
    load_frozen_plan,
    prepare_validation_inputs,
    run_apa_candidates,
    run_asr_tournament,
    run_criterion_tournament,
    run_whisperx_alignment,
)
from speaking_evidence.runner import write_json


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(mapping: dict, name: str) -> str:
    value = mapping.get(name)
    return "n/a" if value is None else f"{value:.4f}"


def write_report(root: Path, final: dict) -> None:
    asr = final["asr"]
    tournament = final["criteria"]
    alignment = final["alignment"]
    apa = final["apa"]
    completeness = final["completeness"]
    asr_rows = []
    for item in asr["candidates"]:
        asr_rows.append(
            f"| {item['candidate_id']} | {_metric(item, 'micro_wer')} | "
            f"{_metric(item, 'mean_wer')} | {_metric(item, 'median_wer')} | "
            f"{item.get('substitutions', 'n/a')} / {item.get('deletions', 'n/a')} / "
            f"{item.get('insertions', 'n/a')} | "
            f"{_metric(item, 'runtime_sec_reference_six')} | "
            f"{item.get('peak_process_tree_ram_bytes', 'n/a')} | "
            f"{item.get('failure_count', 'n/a')} | "
            f"{'YES' if item['candidate_id'] == final['asr_selection']['selected'] else 'NO'} | "
            f"{item.get('status')} |"
        )

    def criterion_table(criterion: str) -> list[str]:
        rows = []
        selected = tournament["selections"][criterion]["selected"]
        for candidate_id, mapping in tournament["mappings"][criterion].items():
            rows.append(
                f"| {candidate_id} | {mapping.get('status')} | {_metric(mapping, 'loo_mae')} | "
                f"{_metric(mapping, 'balanced_accuracy')} | "
                f"{_metric(mapping, 'within_one_band_agreement')} | "
                f"{_metric(mapping, 'spearman_correlation')} | "
                f"{mapping.get('feature_count', 0)} | "
                f"{_metric(mapping, 'supervised_feature_to_n_ratio')} | "
                f"{'YES' if candidate_id == selected else 'NO'} |"
            )
        return rows

    apa_rows = []
    for item in apa["candidates"]:
        candidate = item.get("candidate", {})
        reason = item.get("reason") or (
            f"WINDOWS_PROCESS_EXIT_{item['returncode']}" if item.get("returncode") else "n/a"
        )
        apa_rows.append(
            f"| {candidate.get('candidate_id')} | {candidate.get('subfolder', 'n/a')} | "
            f"{candidate.get('weight_bytes', 'n/a')} | {item.get('status')} | "
            f"{item.get('device', 'n/a')} | {item.get('peak_process_ram_bytes', 'n/a')} | "
            f"{item.get('total_item_runtime_sec', 'n/a')} | "
            f"{'NO' if not item.get('direct_pretrained_scores_emitted') else 'YES'} | {reason} |"
        )
    aligned_items = [item for item in alignment.get("items", []) if item.get("timing_comparison")]
    mean_start = (sum(item["timing_comparison"]["mean_absolute_start_delta_sec"]
                      for item in aligned_items
                      if item["timing_comparison"]["mean_absolute_start_delta_sec"] is not None)
                  / max(1, sum(item["timing_comparison"]["mean_absolute_start_delta_sec"] is not None
                               for item in aligned_items)))
    mean_end = (sum(item["timing_comparison"]["mean_absolute_end_delta_sec"]
                    for item in aligned_items
                    if item["timing_comparison"]["mean_absolute_end_delta_sec"] is not None)
                / max(1, sum(item["timing_comparison"]["mean_absolute_end_delta_sec"] is not None
                             for item in aligned_items)))
    lines = [
        "# PRETRAINED MODEL TOURNAMENT REPORT",
        "",
        "Scope: development-only P2.4 tournament. No holdout media or outcome was used.",
        "",
        f"Frozen plan SHA-256: `{final['plan_sha256']}`",
        "",
        "All NCKH12 metrics below are measured locally. Published external benchmark values were used only to predeclare candidates and are not reported as NCKH12 results.",
        "",
        "## Engineering provenance",
        "",
        "- `WHISPERX_INSTALL_ATTEMPT_1`: dependency-resolution loop; terminated safely; main environment unaffected.",
        "- Final isolated alignment environment: `whisperx==3.8.6`, `torch==2.8.0+cpu`, `transformers==4.57.6`; dependency check passed.",
        "- Main environment remained `torch==2.11.0` (CPU-only), `transformers==5.17.0`, `ctranslate2==4.8.1`.",
        "- RTX 3050 4 GB and one CTranslate2 CUDA device were detected, but the frozen CPU/int8 policy was retained for reproducibility. Peak VRAM was 0 for measured candidates.",
        "- The first small.en materialization attempt hit Windows symlink privilege error 1314. The exact frozen revision was then materialized without symlinks and benchmarked successfully; challengers were not rerun.",
        "",
        "## ASR",
        "",
        "All candidates used CPU, int8, identical audio, normalization and decoding settings.",
        "",
        "| model | micro-WER | mean WER | median WER | S / D / I | six-ref runtime (s) | peak RAM (bytes) | failures | selected | status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
        *asr_rows,
        "",
        f"Selected: `{final['asr_selection']['selected']}` — {final['asr_selection']['reason']}.",
        "",
        "## Alignment",
        "",
        f"WhisperX status: `{alignment.get('status')}`. Canonical transcription was not replaced.",
        f"Mean absolute timing delta where positionally comparable: start={mean_start:.4f}s, end={mean_end:.4f}s.",
        "Both current and WhisperX-derived Fluency evidence are preserved.",
        "",
        "## SSL-FT-PRON pretrained evidence",
        "",
        "| candidate | official subpath | weight bytes | status | device | peak RAM (bytes) | item runtime (s) | direct score | failure/resource note |",
        "|---|---|---:|---|---|---:|---:|---|---|",
        *apa_rows,
        "",
        "The released General/Freeze checkpoint state contains an official four-output training head, but the documented packaged encoder loading path does not provide a sufficiently clear standalone score-inference contract for this tournament. For the successful HuBERT-base fallback, the full wrapper state was loaded with `strict=True`; only its fine-tuned encoder was used. Outputs are therefore labeled `PRETRAINED_EMBEDDING_FEATURE`, never direct pronunciation scores. Mean pooling follows the official method; PCA was fitted without human labels and frozen.",
        "",
        "## Fluency",
        "",
        "| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
        *criterion_table("fluency"),
        "",
        f"Winner: `{tournament['selections']['fluency']['selected']}` — {tournament['selections']['fluency']['reason']}.",
        "Predictions remain constrained to observed human support [4,5].",
        "",
        "## Pronunciation",
        "",
        "| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
        *criterion_table("pronunciation"),
        "",
        f"Winner: `{tournament['selections']['pronunciation']['selected']}` — {tournament['selections']['pronunciation']['reason']}.",
        "Scores remain constrained to [3,4]. No phoneme-level diagnostic claim is made.",
        "",
        "## Intelligibility",
        "",
        "| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
        *criterion_table("intelligibility"),
        "",
        f"Winner/status: `{tournament['selections']['intelligibility']['selected']}` / `{tournament['selections']['intelligibility']['status']}`.",
        "ASR disagreement is recognition-stability evidence, not a pronunciation error.",
        "",
        "## Prosody",
        "",
        "| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
        *criterion_table("prosody"),
        "",
        f"Winner/status: `{tournament['selections']['prosody']['selected']}` / `{tournament['selections']['prosody']['status']}`.",
        "",
        "## Reading Completeness",
        "",
        "The deterministic ASR-assisted method is retained. Backend comparison:",
        "",
        "| ASR backend | mean coverage | matched | omissions | insertions | uncertain substitutions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for backend in completeness["backends"]:
        lines.append(
            f"| {backend['candidate_id']} | {backend['mean_coverage']:.4f} | "
            f"{backend['total_matched']} | {backend['total_omissions']} | "
            f"{backend['total_insertions']} | {backend['total_substitutions_or_uncertain']} |"
        )
    lines.extend([
        "",
        "Differences between ASR backends are not proven learner errors.",
        "",
        "## Frozen five-video validation plan",
        "",
        "Reserved IDs: `D006, D023, D064, D043, D048`. Machine evidence is prepared, but no future human validation rating was read for model selection. Winners are frozen before those ratings are collected.",
        "",
        "## Safety and limitations",
        "",
        "- DEVELOPMENT / PRELIMINARY only.",
        "- NOT CEFR, NOT B2, NOT IELTS.",
        "- N=12 model-selection sample with restricted human ranges.",
        "- Feature/N ratios above 0.25 are explicitly flagged as methodologically unsafe; such candidates cannot be promoted on a marginal metric difference.",
        "- No large speech model was fine-tuned on NCKH12.",
        "- No Overall score was generated.",
        "- Fixed 18-video holdout untouched.",
    ])
    (root / "PRETRAINED_MODEL_TOURNAMENT_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    root = PROJECT_ROOT
    tournament_root = root / "assessment_runs/T001_p24_tournament_v1"
    plan_path = root / "pretrained_model_tournament_v1.json"
    final_path = tournament_root / "tournament_final_summary.json"
    plan, digest = load_frozen_plan(plan_path, final_path)
    split_proof = assert_split_policy(root, tuple(
        plan["data_policy"]["calibration_model_selection_set"]
        + plan["data_policy"]["development_model_validation_set"]))
    if not (tournament_root / "validation_inputs_summary.json").is_file():
        prepare_validation_inputs(root, tournament_root)
    asr_path = tournament_root / "asr_tournament_summary.json"
    asr = _load(asr_path) if asr_path.is_file() else run_asr_tournament(
        root, plan, tournament_root, root / ".local/p24_models")
    multi = build_multi_asr_features(root, plan, tournament_root)
    whisperx_python = root / ".local/p24-whisperx/Scripts/python.exe"
    alignment_path = tournament_root / "whisperx_alignment_summary.json"
    if alignment_path.is_file():
        alignment_raw = _load(alignment_path)
    elif whisperx_python.is_file():
        alignment_raw = run_whisperx_alignment(root, plan, tournament_root, whisperx_python)
    else:
        alignment_raw = {"version": VERSION, "status": "BACKEND_UNAVAILABLE",
                         "reason": "ISOLATED_WHISPERX_ENVIRONMENT_MISSING", "items": [],
                         "canonical_evidence_overwritten": False, "holdout_processed": False}
        write_json(alignment_path, alignment_raw)
    alignment = build_whisperx_fluency(root, tournament_root)
    apa_path = tournament_root / "apa_tournament_summary.json"
    apa = _load(apa_path) if apa_path.is_file() else run_apa_candidates(
        root, plan, tournament_root)
    build_apa_pca_features(plan, tournament_root)
    completeness = build_completeness_by_asr(root, plan, tournament_root)
    criteria = run_criterion_tournament(root, plan, digest, tournament_root)
    asr_selection = _asr_selection(plan, asr)
    final = {"version": VERSION, "status": "PRETRAINED_MODEL_TOURNAMENT_COMPLETE",
             "plan_sha256": digest, "split_proof": split_proof, "asr": asr,
             "asr_selection": asr_selection, "multi_asr": multi,
             "alignment_raw": alignment_raw, "alignment": alignment,
             "apa": apa, "completeness": completeness, "criteria": criteria,
             "model_selection_frozen": True, "validation_human_ratings_read": False,
             "overall_score_created": False, "holdout_processed": False,
             "runtime": {"python": sys.version, "platform": platform.platform()}}
    write_json(final_path, final)
    write_report(root, final)
    print("[P2.4] tournament complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
