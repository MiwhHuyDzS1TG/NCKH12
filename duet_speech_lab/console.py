"""Run tracking, review, ground truth, evaluation, audio, and timeline helpers.

The UI calls these helpers; all signal processing stays in duet_segmenter.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import soundfile as sf

from duet_segmenter.evaluation import LABELS, evaluate, load_ground_truth, provisional_gates
from duet_segmenter.pipeline import run

REVIEW_LABELS = ["UNREVIEWED", "LEARNER", "ORIGINAL", "OVERLAP", "SILENCE", "IGNORE"]
GT_LABELS = ["ORIGINAL", "LEARNER", "OVERLAP", "SILENCE", "OUTSIDE_TEMPLATE"]
REVIEW_COLUMNS = ["segment_id", "start", "end", "duration", "predicted_label", "confidence",
                  "overlap_candidate", "review_label", "notes"]
MANUAL_COLUMNS = ["start", "end", "label", "notes"]


def safe_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", Path(name).stem).encode("ascii", "ignore").decode("ascii")
    return (re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower() or "video")[:40]


def config_hash(config: dict) -> str:
    encoded = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_name(source: str | Path | BinaryIO) -> str:
    if isinstance(source, (str, Path)):
        return Path(source).name
    return Path(getattr(source, "name", "upload.mp4")).name


def _stage_source(source: str | Path | BinaryIO, target_dir: Path, role: str) -> tuple[Path, dict]:
    name = _source_name(source)
    suffix = Path(name).suffix.lower()
    if not suffix or not re.fullmatch(r"\.[a-z0-9]{2,8}", suffix):
        suffix = ".mp4"
    destination = target_dir/f"{role}{suffix}"
    if isinstance(source, (str, Path)):
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{role} video does not exist: {path}")
        shutil.copy2(path, destination)
    else:
        if hasattr(source, "seek"):
            source.seek(0)
        with destination.open("wb") as handle:
            shutil.copyfileobj(source, handle, length=1024*1024)
    if destination.stat().st_size == 0:
        raise ValueError(f"{role} video is empty: {name}")
    return destination, {"original_name": name, "stored_path": str(destination),
                         "size_bytes": destination.stat().st_size, "sha256": _file_hash(destination)}


def execute_analysis(original_source: str | Path | BinaryIO, duet_source: str | Path | BinaryIO,
                     config: dict, run_root: str | Path,
                     progress_callback: Callable[[str, float], None] | None = None) -> tuple[Path, dict]:
    """Copy inputs and exact config into a dated run folder, then call v0.1 once."""
    root = Path(run_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+safe_name(_source_name(duet_source))
    run_dir = None
    for index in range(1, 100):
        candidate = root/(base if index == 1 else f"{base}_{index:02d}")
        try:
            candidate.mkdir()
            run_dir = candidate
            break
        except FileExistsError:
            continue
    if run_dir is None:
        raise RuntimeError("Could not allocate a unique run directory")
    inputs = run_dir/"inputs"
    inputs.mkdir()
    config_copy = json.loads(json.dumps(config))
    (run_dir/"config.json").write_text(json.dumps(config_copy, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    manifest = {"run_id": run_dir.name, "created_at": datetime.now().isoformat(timespec="seconds"),
                "config_sha256_short": config_hash(config_copy), "status": "running"}
    try:
        original_path, manifest["original_input"] = _stage_source(original_source, inputs, "original")
        duet_path, manifest["duet_input"] = _stage_source(duet_source, inputs, "duet")
        (run_dir/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        result = run(original_path, duet_path, run_dir, config_copy, progress_callback=progress_callback)
        manifest["status"] = result["status"]
        manifest["runtime_sec"] = result["runtime_sec"]
        (run_dir/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        return run_dir, result
    except Exception as exc:
        manifest["status"] = "error"
        manifest["error"] = str(exc)
        (run_dir/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        raise


def recent_runs(run_root: str | Path, limit: int = 20) -> list[Path]:
    root = Path(run_root)
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and (p/"result.json").is_file()),
                  key=lambda p: p.name, reverse=True)[:limit]


def load_result(run_dir: str | Path) -> dict:
    return json.loads((Path(run_dir)/"result.json").read_text(encoding="utf-8"))


def review_dataframe(result: dict) -> pd.DataFrame:
    rows = []
    for index, item in enumerate(result.get("learner_segments", []), start=1):
        rows.append({"segment_id": item.get("segment_id", f"S{index:03d}"), "start": float(item["start"]),
                     "end": float(item["end"]), "duration": float(item["end"]-item["start"]),
                     "predicted_label": "LEARNER", "confidence": item.get("confidence"),
                     "overlap_candidate": bool(item.get("overlap_candidate", False)),
                     "review_label": "UNREVIEWED", "notes": ""})
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS)


def empty_manual_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=MANUAL_COLUMNS).astype({"start": "float64", "end": "float64",
                                                        "label": "str", "notes": "str"})


def load_review(run_dir: str | Path, result: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = Path(run_dir)/"review.json"
    if not path.exists():
        return review_dataframe(result), empty_manual_dataframe()
    data = json.loads(path.read_text(encoding="utf-8"))
    review = pd.DataFrame(data.get("reviewed_segments", []), columns=REVIEW_COLUMNS)
    manual = pd.DataFrame(data.get("manual_annotations", []), columns=MANUAL_COLUMNS)
    return review, manual


def review_metadata(run_dir: str | Path) -> dict:
    path = Path(run_dir)/"review.json"
    if not path.exists():
        return {"full_video_reviewed_for_missed_speech": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"full_video_reviewed_for_missed_speech": bool(data.get("full_video_reviewed_for_missed_speech", False)),
            "review_provenance": data.get("review_provenance", "")}


def accept_all_predictions(review: pd.DataFrame) -> pd.DataFrame:
    """Create an editable human-review draft; predictions remain immutable."""
    draft = review.copy()
    draft["review_label"] = "LEARNER"
    return draft


def validate_review(review: pd.DataFrame, result: dict) -> pd.DataFrame:
    expected = review_dataframe(result)
    if len(review) != len(expected) or review["segment_id"].tolist() != expected["segment_id"].tolist():
        raise ValueError("Review rows must match the immutable predicted segment IDs")
    clean = review.copy()
    duration = float(result["timeline"]["duet_duration_sec"])
    for column in ("start", "end"):
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    for _, row in clean.iterrows():
        if (pd.isna(row["start"]) or pd.isna(row["end"]) or row["start"] < 0
                or row["end"] <= row["start"] or row["end"] > duration+1e-6):
            raise ValueError(f"Invalid corrected interval for {row['segment_id']}: start ≥ 0, end > start, end ≤ {duration:.3f} s")
        if row["review_label"] not in REVIEW_LABELS:
            raise ValueError(f"Invalid review label for {row['segment_id']}: {row['review_label']}")
    clean["duration"] = clean["end"]-clean["start"]
    clean["notes"] = clean["notes"].fillna("").astype(str)
    return clean


def validate_manual(manual: pd.DataFrame, duration: float) -> pd.DataFrame:
    if manual.empty:
        return empty_manual_dataframe()
    clean = manual.copy()
    for column in ("start", "end"):
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    # Streamlit's dynamic editor may leave a fully blank row while adding one.
    clean = clean.dropna(subset=["start", "end", "label"], how="all")
    for index, row in clean.iterrows():
        label = str(row["label"]).upper() if not pd.isna(row["label"]) else ""
        if (pd.isna(row["start"]) or pd.isna(row["end"]) or row["start"] < 0 or
                row["end"] <= row["start"] or row["end"] > duration+1e-6 or label not in LABELS):
            raise ValueError(f"Invalid manual ground-truth row {index+1}; use start ≥ 0, end > start, end ≤ Duet duration, and a valid label")
        clean.at[index, "label"] = label
    clean["notes"] = clean["notes"].fillna("").astype(str)
    return clean


def ground_truth_rows(review: pd.DataFrame, manual: pd.DataFrame, result: dict) -> list[dict]:
    duration = float(result["timeline"]["duet_duration_sec"])
    review = validate_review(review, result)
    manual = validate_manual(manual, duration)
    rows = [{"start": float(row["start"]), "end": float(row["end"]), "label": row["review_label"]}
            for _, row in review.iterrows() if row["review_label"] in GT_LABELS]
    rows += [{"start": float(row["start"]), "end": float(row["end"]), "label": row["label"]}
             for _, row in manual.iterrows()]
    rows.sort(key=lambda x: (x["start"], x["end"]))
    for previous, current in zip(rows, rows[1:]):
        if current["start"] < previous["end"]-1e-6:
            raise ValueError(f"Ground-truth intervals overlap at {current['start']:.3f} s; adjust reviewed/manual boundaries before export")
    return rows


def save_review(run_dir: str | Path, review: pd.DataFrame, manual: pd.DataFrame,
                result: dict, full_video_reviewed: bool = False,
                review_provenance: str = "Research Console human review") -> tuple[Path | None, list[dict]]:
    run_dir = Path(run_dir)
    clean_review = validate_review(review, result)
    clean_manual = validate_manual(manual, result["timeline"]["duet_duration_sec"])
    gt_rows = ground_truth_rows(clean_review, clean_manual, result)
    payload = {"saved_at": datetime.now().isoformat(timespec="seconds"),
               "prediction_file": "learner_segments.json", "reviewed_segments": json.loads(clean_review.to_json(orient="records")),
               "manual_annotations": json.loads(clean_manual.to_json(orient="records")),
               "full_video_reviewed_for_missed_speech": bool(full_video_reviewed),
               "review_provenance": review_provenance}
    (run_dir/"review.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    gt_path = run_dir/"ground_truth.csv"
    if gt_rows:
        with gt_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["start", "end", "label"])
            writer.writeheader()
            writer.writerows(gt_rows)
        return gt_path, gt_rows
    if gt_path.exists():
        gt_path.unlink()
    return None, []


def labeled_coverage(rows: list[dict], duration: float) -> float:
    if duration <= 0:
        return 0.
    return min(1., sum(max(0., min(duration, x["end"])-max(0., x["start"])) for x in rows)/duration)


def evaluate_run(run_dir: str | Path, result: dict, config: dict) -> dict:
    run_dir = Path(run_dir)
    gt_path = run_dir/"ground_truth.csv"
    if not gt_path.is_file():
        raise FileNotFoundError("Save at least one reviewed/manual ground-truth interval first")
    duration = float(result["timeline"]["duet_duration_sec"])
    truth = load_ground_truth(gt_path, duration)
    metrics = evaluate(result["learner_segments"], result["overlap_candidates"],
                       result["outside_template_detections"], truth, duration, config["evaluation"])
    metrics["provisional_gates"] = provisional_gates(metrics)
    metrics["ground_truth_coverage"] = labeled_coverage(truth, duration)
    metadata = review_metadata(run_dir)
    metrics["full_video_reviewed_for_missed_speech"] = metadata["full_video_reviewed_for_missed_speech"]
    metrics["validation_scope"] = ("complete_timeline" if metrics["ground_truth_coverage"] >= 0.99 else
                                   "reviewed_intervals_only")
    metrics["ground_truth_status"] = ("FULL TIMELINE" if metrics["ground_truth_coverage"] >= 0.99 else
                                      "DEVELOPMENT/PARTIAL GROUND TRUTH")
    if not metrics["full_video_reviewed_for_missed_speech"]:
        metrics["learner_recall_display"] = "NOT FULLY VERIFIED"
        metrics["learner_f1_display"] = "NOT FULLY VERIFIED"
    (run_dir/"evaluation.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return metrics


def audio_clip_bytes(source_wav: str | Path, start: float, end: float,
                     context_sec: float = 0.) -> tuple[bytes, float, float, int, int]:
    """Read only a Duet source interval; never open the residual detection WAV."""
    with sf.SoundFile(source_wav) as source:
        duration = len(source)/source.samplerate
        lo = max(0., start-context_sec)
        hi = min(duration, end+context_sec)
        if hi <= lo:
            raise ValueError("Audio review interval must have end > start")
        source.seek(round(lo*source.samplerate))
        data = source.read(max(1,round((hi-lo)*source.samplerate)), dtype="float32", always_2d=True)
        buffer = io.BytesIO()
        sf.write(buffer, data, source.samplerate, format="WAV", subtype="PCM_16")
        return buffer.getvalue(), lo, hi, source.samplerate, source.channels


def summary_metrics(result: dict) -> dict:
    anchors = [float(x["correlation"]) for x in result["alignment_diagnostics"].get("anchors", []) if x.get("accepted")]
    cancel = result.get("cancellation_diagnostics") or {}
    return {"status": result["status"],
            "original_duration": result["input_metadata"]["original"]["duration_sec"],
            "duet_duration": result["input_metadata"]["duet"]["duration_sec"],
            "offset": result["alignment_diagnostics"].get("b"),
            "anchor_min": min(anchors) if anchors else None,
            "anchor_median": float(np.median(anchors)) if anchors else None,
            "anchor_max": max(anchors) if anchors else None,
            "reference_gain": cancel.get("estimated_reference_gain"),
            "suppression_db": cancel.get("reference_suppression_db"),
            "backend": cancel.get("backend"),
            "runtime": result.get("runtime_sec"),
            "learner_count": len(result.get("learner_segments", [])),
            "learner_duration": sum(x["end"]-x["start"] for x in result.get("learner_segments", [])),
            "overlap_count": len(result.get("overlap_candidates", [])),
            "outside_count": len(result.get("outside_template_detections", []))}


def timeline_figure(result: dict, show_residual: bool = False) -> go.Figure:
    rows = [
        ("ORIGINAL", result.get("original_vad_segments", []), "#64748b"),
        ("PREDICTED_LEARNER", result.get("learner_segments", []), "#0f766e"),
        ("OVERLAP", result.get("overlap_candidates", []), "#c45663"),
        ("OUTSIDE_TEMPLATE", result.get("outside_template_detections", []), "#9a7b33"),
    ]
    if show_residual:
        rows.append(("RESIDUAL_VAD", result.get("residual_vad_segments", []), "#d18b47"))
    fig = go.Figure()
    order = [row[0] for row in rows]
    for label, intervals, color in rows:
        # A zero-width transparent bar keeps empty diagnostic rows visible.
        has_intervals = bool(intervals)
        fig.add_trace(go.Bar(
            name=label.replace("_", " ").title(), orientation="h", y=[label]*len(intervals) if has_intervals else [label],
            x=[float(s["end"]-s["start"]) for s in intervals] if has_intervals else [0.],
            base=[float(s["start"]) for s in intervals] if has_intervals else [0.],
            width=0.62, marker_color=color, marker_line_width=0,
            marker_opacity=1 if has_intervals else 0,
            customdata=[[label, float(s["start"]), float(s["end"]), float(s["end"]-s["start"]),
                         s.get("confidence"), bool(s.get("overlap_candidate", label == "OVERLAP"))] for s in intervals]
                         if has_intervals else [[label, 0., 0., 0., None, False]],
            hoverinfo="all" if has_intervals else "skip",
            hovertemplate="<b>%{customdata[0]}</b><br>Start: %{customdata[1]:.3f} s<br>End: %{customdata[2]:.3f} s"
                          "<br>Duration: %{customdata[3]:.3f} s<br>Confidence: %{customdata[4]}"
                          "<br>Overlap flag: %{customdata[5]}<extra></extra>",
        ))
    fig.add_trace(go.Scatter(x=[0.]*len(order), y=order, mode="markers",
                             marker=dict(size=1, opacity=0), hoverinfo="skip", showlegend=False,
                             name="row labels"))
    duration = float(result["timeline"]["duet_duration_sec"])
    template_start = float(result["timeline"]["template_start_sec"])
    template_end = float(result["timeline"]["template_end_sec"])
    fig.add_vrect(x0=template_start, x1=template_end, fillcolor="#ecf3ed", opacity=0.32,
                  layer="below", line_width=0)
    fig.add_vline(x=template_end, line_color="#7c8793", line_dash="dash", line_width=1)
    fig.update_layout(height=390 if not show_residual else 450, barmode="overlay",
                      margin=dict(l=10, r=10, t=24, b=35), showlegend=False,
                      paper_bgcolor="white", plot_bgcolor="white", font=dict(family="Arial", size=12),
                      xaxis=dict(title="Duet timeline (seconds)", range=[0, duration], showgrid=True, gridcolor="#e8eef0"),
                      yaxis=dict(categoryorder="array", categoryarray=order[::-1], showgrid=False))
    return fig
