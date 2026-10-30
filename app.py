"""Duet Speech Lab — local Research Console v0.2.

Start with: streamlit run app.py
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# The project may have workspace-local dependencies from the v0.1 development pass.
if (ROOT/".vendor").is_dir():
    sys.path.insert(0, str(ROOT/".vendor"))

import pandas as pd
import streamlit as st

from duet_segmenter.pipeline import load_config
from duet_segmenter.optimization import optimize_vad, predict_candidate
from duet_segmenter.cohort import audit_outcome, run_cohort
from duet_segmenter.profile import build_template_profile
from duet_speech_lab.console import (
    GT_LABELS, REVIEW_LABELS, accept_all_predictions, audio_clip_bytes, config_hash, empty_manual_dataframe,
    evaluate_run, execute_analysis, load_result, load_review, recent_runs, safe_name,
    review_metadata, save_review, summary_metrics, timeline_figure, validate_review,
)

RUNS = Path(os.environ.get("DUET_SPEECH_LAB_RUNS", str(ROOT/"runs"))).expanduser().resolve()
COHORT_RUNS = Path(os.environ.get("DUET_SPEECH_LAB_COHORTS", str(ROOT/"cohort_runs"))).expanduser().resolve()

st.set_page_config(page_title="Duet Speech Lab", page_icon="🎙️", layout="wide",
                   initial_sidebar_state="expanded")
st.markdown("""
<style>
  .block-container {max-width: 1550px; padding-top: 3.8rem; padding-bottom: 4rem;}
  h1, h2, h3 {letter-spacing: -0.025em;}
  div[data-testid="stMetric"] {background: #f7faf9; border: 1px solid #e2eae7;
    border-radius: 10px; padding: 12px 15px; min-height: 102px;}
  div[data-testid="stMetricLabel"] {color: #53696a; font-size: 0.85rem;}
  .lab-kicker {font-size: .78rem; font-weight: 700; letter-spacing: .15em;
    text-transform: uppercase; color: #0f766e; margin-bottom: .35rem;}
  .lab-subtitle {color: #637879; margin-top: -.55rem; margin-bottom: 1.4rem;}
  .lab-run-id {font-size: .88rem; color: #506667; padding: .5rem 0;}
</style>
""", unsafe_allow_html=True)


def _format_number(value: float | None, suffix: str = "", digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}{suffix}"


def _sidebar_config() -> dict:
    defaults = load_config()
    st.sidebar.header("Experiment controls")
    if st.sidebar.button("Reset to defaults", width="stretch"):
        for key in ["lab_vad_threshold", "lab_min_speech", "lab_min_silence", "lab_speech_pad",
                    "lab_merge_gap", "lab_cancel_backend", "lab_leakage_enabled"]:
            st.session_state.pop(key, None)
        st.rerun()
    cfg = copy.deepcopy(defaults)
    cfg["vad"]["threshold"] = st.sidebar.slider("VAD threshold", 0.10, 0.95,
                                                  float(defaults["vad"]["threshold"]), 0.05,
                                                  key="lab_vad_threshold")
    cfg["vad"]["min_speech_duration_ms"] = st.sidebar.slider("Minimum speech (ms)", 50, 1000,
                            int(defaults["vad"]["min_speech_duration_ms"]), 25, key="lab_min_speech")
    cfg["vad"]["min_silence_duration_ms"] = st.sidebar.slider("Minimum silence (ms)", 0, 1000,
                            int(defaults["vad"]["min_silence_duration_ms"]), 25, key="lab_min_silence")
    cfg["vad"]["speech_pad_ms"] = st.sidebar.slider("Speech padding (ms)", 0, 300,
                            int(defaults["vad"]["speech_pad_ms"]), 10, key="lab_speech_pad")
    cfg["segments"]["merge_gap_sec"] = st.sidebar.slider("Merge gap (s)", 0.0, 1.0,
                            float(defaults["segments"]["merge_gap_sec"]), 0.02, key="lab_merge_gap")
    backend_ui = st.sidebar.selectbox("Cancellation backend", ["auto", "linear", "aec3"],
                            index=["auto", "linear", "aec3"].index(
                                "aec3" if defaults["cancellation"]["backend"] == "webrtc"
                                else defaults["cancellation"]["backend"]), key="lab_cancel_backend")
    cfg["cancellation"]["backend"] = "webrtc" if backend_ui == "aec3" else backend_ui
    cfg["leakage"]["enabled"] = st.sidebar.checkbox("Filter strong reference leakage",
        value=bool(defaults["leakage"]["enabled"]), key="lab_leakage_enabled")
    st.sidebar.caption(f"Config hash for next run: `{config_hash(cfg)}`")
    return cfg


def _input_panel(config: dict) -> None:
    st.subheader("1 · Inputs and analysis")
    with st.container(border=True):
        source_mode = st.radio("Video source", ["Workspace videos", "Upload videos"],
                               horizontal=True, key="lab_source_mode")
        original_source = duet_source = None
        if source_mode == "Workspace videos":
            videos = sorted(ROOT.glob("*.mp4"), key=lambda p: p.name.lower())
            if not videos:
                st.info("No MP4 videos in the workspace. Use Upload videos.")
            else:
                names = [p.name for p in videos]
                left, right = st.columns(2)
                with left:
                    original_name = st.selectbox("Original template", names,
                              index=names.index("template.mp4") if "template.mp4" in names else 0,
                              key="lab_original_name")
                with right:
                    duet_name = st.selectbox("Completed Duet", names,
                              index=names.index("main video.mp4") if "main video.mp4" in names else min(1, len(names)-1),
                              key="lab_duet_name")
                original_source, duet_source = ROOT/original_name, ROOT/duet_name
        else:
            left, right = st.columns(2)
            with left:
                original_source = st.file_uploader("Original template", type=["mp4", "mov", "mkv"],
                                                   key="lab_original_upload")
            with right:
                duet_source = st.file_uploader("Completed Duet", type=["mp4", "mov", "mkv"],
                                               key="lab_duet_upload")
        if st.button("Run Analysis", type="primary", disabled=original_source is None or duet_source is None,
                     key="lab_run_button"):
            if original_source is not None and duet_source is not None and original_source == duet_source:
                st.error("Choose two different videos: the original template and the completed Duet.")
                return
            with st.status("Analyzing videos…", expanded=True) as status:
                progress = st.progress(0, text="Preparing run")

                def update(stage: str, fraction: float) -> None:
                    progress.progress(min(100, max(0, round(fraction*100))), text=stage)
                    st.write(stage)

                try:
                    run_dir, result = execute_analysis(original_source, duet_source, config, RUNS, update)
                except (OSError, RuntimeError, ValueError, KeyError) as exc:
                    status.update(label="Analysis failed", state="error", expanded=True)
                    st.error(str(exc))
                else:
                    st.session_state["lab_active_run"] = str(run_dir)
                    st.session_state.pop("lab_loaded_review_run", None)
                    status.update(label=f"Run {run_dir.name}: {result['status']}",
                                  state="complete" if result["status"] == "ok" else "error", expanded=False)
                    st.success(f"Analysis saved in runs/{run_dir.name}")


def _run_history() -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Recent runs")
    runs = recent_runs(RUNS, 12)
    if not runs:
        st.sidebar.caption("No saved runs yet.")
        return
    if "lab_active_run" not in st.session_state:
        st.session_state["lab_active_run"] = str(runs[0])
    for path in runs:
        selected = st.session_state.get("lab_active_run") == str(path)
        if st.sidebar.button(("● " if selected else "○ ")+path.name, key=f"lab_history_{path.name}",
                             width="stretch"):
            st.session_state["lab_active_run"] = str(path)
            st.session_state.pop("lab_loaded_review_run", None)
            st.rerun()


def _summary(result: dict, run_dir: Path) -> None:
    metrics = summary_metrics(result)
    manifest_path = run_dir/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    st.markdown(f"<div class='lab-run-id'>Run ID: <b>{run_dir.name}</b> · saved config hash: "
                f"<b>{manifest.get('config_sha256_short', '—')}</b></div>", unsafe_allow_html=True)
    st.subheader("2 · Run summary")
    items = [
        ("Pipeline status", metrics["status"]),
        ("Original duration", _format_number(metrics["original_duration"], " s", 2)),
        ("Duet duration", _format_number(metrics["duet_duration"], " s", 2)),
        ("Alignment offset", _format_number(metrics["offset"], " s", 6)),
        ("Anchor correlation · min", _format_number(metrics["anchor_min"], digits=3)),
        ("Anchor correlation · median", _format_number(metrics["anchor_median"], digits=3)),
        ("Anchor correlation · max", _format_number(metrics["anchor_max"], digits=3)),
        ("Reference gain", _format_number(metrics["reference_gain"], digits=4)),
        ("Reference suppression", _format_number(metrics["suppression_db"], " dB", 2)),
        ("Cancellation backend", metrics["backend"] or "—"),
        ("Runtime", _format_number(metrics["runtime"], " s", 2)),
        ("Learner segments", str(metrics["learner_count"])),
        ("Predicted learner duration", _format_number(metrics["learner_duration"], " s", 2)),
        ("Overlap candidates", str(metrics["overlap_count"])),
        ("Outside-template detections", str(metrics["outside_count"])),
    ]
    for start in range(0, len(items), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, items[start:start+4]):
            column.metric(label, value)
    if result.get("warnings"):
        for warning in result["warnings"]:
            st.warning(warning)
    comparison = result.get("backend_comparison")
    if comparison:
        st.caption(f"AUTO compared {len(comparison['candidates'])} full-length cancellation outputs and chose "
                   f"{comparison['selected_backend']} using measured suppression and residue checks.")


def _audio_review(run_dir: Path, start: float, end: float, key: str) -> None:
    source = run_dir/"duet_source_audio.wav"
    if not source.is_file():
        st.error("Unprocessed Duet source audio is missing; do not substitute residual_detection.wav.")
        return
    choice = st.radio("Audio review", ["Selected interval", "±0.5 s context", "±1.0 s context"],
                      horizontal=True, key=key)
    context = {"Selected interval": 0., "±0.5 s context": 0.5, "±1.0 s context": 1.0}[choice]
    try:
        clip, lo, hi, sr, channels = audio_clip_bytes(source, start, end, context)
    except (OSError, ValueError) as exc:
        st.error(str(exc))
        return
    st.caption(f"From unprocessed Duet source audio · {lo:.3f}–{hi:.3f} s · {sr:,} Hz · {channels} channel(s)")
    st.audio(clip, format="audio/wav")


def _load_review_state(run_dir: Path, result: dict) -> None:
    if st.session_state.get("lab_loaded_review_run") != str(run_dir):
        review, manual = load_review(run_dir, result)
        st.session_state["lab_review_df"] = review
        st.session_state["lab_manual_df"] = manual
        st.session_state[f"lab_full_review_{run_dir.name}"] = review_metadata(run_dir)["full_video_reviewed_for_missed_speech"]
        st.session_state["lab_quick_index"] = 0
        st.session_state["lab_loaded_review_run"] = str(run_dir)
        st.session_state.pop("lab_review_mode", None)
        st.session_state.pop("lab_current_metrics", None)


def _review_table(run_dir: Path, result: dict) -> None:
    st.caption("Edit start/end and the human review label. Predictions and confidence stay unchanged.")
    review = st.data_editor(
        st.session_state["lab_review_df"], key=f"lab_review_editor_{run_dir.name}",
        hide_index=True, height=500, width="stretch", num_rows="fixed",
        disabled=["segment_id", "duration", "predicted_label", "confidence", "overlap_candidate"],
        column_config={
            "segment_id": st.column_config.TextColumn("ID", width="small"),
            "start": st.column_config.NumberColumn("Start (s)", format="%.3f", min_value=0., step=0.001),
            "end": st.column_config.NumberColumn("End (s)", format="%.3f", min_value=0., step=0.001),
            "duration": st.column_config.NumberColumn("Duration (s)", format="%.3f"),
            "predicted_label": st.column_config.TextColumn("Predicted label"),
            "confidence": st.column_config.NumberColumn("Confidence", format="%.3f"),
            "overlap_candidate": st.column_config.CheckboxColumn("Overlap?"),
            "review_label": st.column_config.SelectboxColumn("Human review", options=REVIEW_LABELS, required=True),
            "notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )
    st.session_state["lab_review_df"] = review
    try:
        clean = validate_review(review, result)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state["lab_review_df"] = clean
    ids = clean["segment_id"].tolist()
    if ids:
        selected = st.selectbox("Choose table row to hear", ids, key=f"lab_audio_selected_{run_dir.name}")
        row = clean.loc[clean["segment_id"] == selected].iloc[0]
        st.caption(f"{selected} · {row['start']:.3f}–{row['end']:.3f} s · reviewed label: {row['review_label']}")
        _audio_review(run_dir, float(row["start"]), float(row["end"]), f"lab_audio_context_{run_dir.name}")


def _quick_review(run_dir: Path, result: dict) -> None:
    review = st.session_state["lab_review_df"]
    if st.button("Accept all predicted learner segments · review draft", key=f"lab_accept_all_{run_dir.name}"):
        st.session_state["lab_review_df"] = accept_all_predictions(review)
        st.session_state.pop(f"lab_review_editor_{run_dir.name}", None)
        st.rerun()
    if review.empty:
        st.info("No learner candidates to review in this run.")
        return
    index = min(max(0, int(st.session_state.get("lab_quick_index", 0))), len(review)-1)
    row = review.iloc[index]
    previous, center, next_col = st.columns([1, 3, 1])
    if previous.button("← Previous", disabled=index == 0, key="lab_quick_previous", width="stretch"):
        st.session_state["lab_quick_index"] = index-1
        st.rerun()
    center.markdown(f"**Interval {index+1} of {len(review)} · {row['segment_id']}**  "
                    f"{row['start']:.3f}–{row['end']:.3f} s · confidence {row['confidence']:.3f} · "
                    f"review: **{row['review_label']}**")
    if next_col.button("Next →", disabled=index == len(review)-1, key="lab_quick_next", width="stretch"):
        st.session_state["lab_quick_index"] = index+1
        st.rerun()
    if bool(row["overlap_candidate"]):
        st.warning("Possible overlap: the template and residual VAD are both active here.")
    _audio_review(run_dir, float(row["start"]), float(row["end"]), f"lab_quick_audio_context_{run_dir.name}")
    actions = [("ACCEPT_LEARNER", "LEARNER"), ("ORIGINAL_CONTAMINATION", "ORIGINAL"),
               ("TRUE_OVERLAP", "OVERLAP"), ("SILENCE_FALSE_DETECTION", "SILENCE"),
               ("NEEDS_BOUNDARY_EDIT", None)]
    columns = st.columns(len(actions))
    for column, (label, assigned) in zip(columns, actions):
        if column.button(label, key=f"lab_quick_{safe_name(label)}", width="stretch"):
            updated = review.copy()
            if assigned is None:
                updated.at[updated.index[index], "notes"] = "NEEDS_BOUNDARY_EDIT"
                st.session_state["lab_force_table_review"] = True
                st.session_state[f"lab_audio_selected_{run_dir.name}"] = row["segment_id"]
            else:
                updated.at[updated.index[index], "review_label"] = assigned
                st.session_state["lab_quick_index"] = min(index+1, len(updated)-1)
            st.session_state["lab_review_df"] = updated
            st.session_state.pop(f"lab_review_editor_{run_dir.name}", None)
            st.rerun()


def _evaluation_metrics(metrics: dict) -> None:
    coverage = metrics.get("ground_truth_coverage", 0.)
    if coverage < 0.99:
        st.warning(f"Ground truth covers {coverage:.1%} of the Duet. The numbers below describe labeled intervals only; "
                   "missing learner turns outside them are not counted. Complete the timeline before claiming full recall.")
    else:
        st.success(f"Ground truth covers {coverage:.1%} of the Duet timeline.")
    labels = [
        ("Learner precision", "learner_precision", "%"),
        ("Original contamination", "original_contamination_rate", "%"),
        ("Overlap recall", "overlap_recall", "%"),
        ("False speech outside template", "false_speech_outside_template", "%"),
        ("Median boundary error", "median_boundary_error_sec", " s"),
    ]
    if metrics.get("full_video_reviewed_for_missed_speech"):
        labels[1:1] = [("Learner recall · development", "learner_recall", "%"),
                       ("Learner F1 · development", "learner_f1", "%")]
    else:
        st.warning("Recall / F1: NOT FULLY VERIFIED. Tick the full-Duet review checkbox only after checking for missed learner speech.")
    measured = [(label, key, unit) for label, key, unit in labels if metrics.get(key) is not None]
    for start in range(0, len(measured), 4):
        columns = st.columns(4)
        for column, (label, key, unit) in zip(columns, measured[start:start+4]):
            value = metrics[key]*100 if unit == "%" else metrics[key]
            column.metric(label, f"{value:.1f}{unit}" if unit == "%" else f"{value:.3f}{unit}")
    if not measured:
        st.info("No evaluation metrics are measurable from the saved labels yet.")
    gate_names = {"learner_precision": "Precision ≥ 95%", "learner_recall": "Recall ≥ 95%",
                  "original_contamination_rate": "Original contamination ≤ 3%",
                  "median_boundary_error_sec": "Boundary error ≤ 0.25 s"}
    gate_rows = []
    for key, passed in metrics.get("provisional_gates", {}).items():
        if passed is None or (key == "learner_recall" and not metrics.get("full_video_reviewed_for_missed_speech")):
            continue
        state = "FAIL" if not passed else ("PASS" if coverage >= 0.99 else "WARNING · partial labels")
        gate_rows.append({"Provisional gate": gate_names.get(key, key), "State": state})
    if gate_rows:
        st.dataframe(pd.DataFrame(gate_rows), hide_index=True, width="stretch")


def _validation(run_dir: Path, result: dict, config: dict) -> None:
    st.subheader("5 · Validation")
    st.caption("Human review is saved separately from immutable predictions. Add manual intervals for missed learner speech, "
               "original-only speech, silence, or outside-template regions before treating recall as complete.")
    st.markdown("**Additional ground-truth intervals**")
    if st.button("+ Add missed learner interval", key=f"lab_add_missed_{run_dir.name}"):
        draft = st.session_state.get("lab_manual_df", empty_manual_dataframe())
        st.session_state["lab_manual_df"] = pd.concat([draft, pd.DataFrame([{
            "start": 0., "end": 0., "label": "LEARNER", "notes": "Missed learner interval — edit boundaries"}])], ignore_index=True)
        st.session_state.pop(f"lab_manual_editor_{run_dir.name}", None)
        st.rerun()
    manual = st.data_editor(
        st.session_state.get("lab_manual_df", empty_manual_dataframe()),
        key=f"lab_manual_editor_{run_dir.name}", hide_index=True, num_rows="dynamic", width="stretch",
        column_config={
            "start": st.column_config.NumberColumn("Start (s)", min_value=0., format="%.3f", step=0.001),
            "end": st.column_config.NumberColumn("End (s)", min_value=0., format="%.3f", step=0.001),
            "label": st.column_config.SelectboxColumn("Label", options=GT_LABELS),
            "notes": st.column_config.TextColumn("Notes"),
        },
    )
    st.session_state["lab_manual_df"] = manual
    full_reviewed = st.checkbox("I reviewed the complete Duet for missed learner speech",
                                key=f"lab_full_review_{run_dir.name}")
    st.caption("This confirms a complete search for missed learner speech. Unlabeled Original/silence regions still limit negative-case metrics.")
    left, right = st.columns([1, 1])
    save_clicked = left.button("Save corrections + ground truth", type="primary",
                               key=f"lab_save_{run_dir.name}", width="stretch")
    evaluate_clicked = right.button("Evaluate", key=f"lab_evaluate_{run_dir.name}", width="stretch")
    if save_clicked or evaluate_clicked:
        try:
            gt_path, rows = save_review(run_dir, st.session_state["lab_review_df"], manual, result,
                                        full_video_reviewed=full_reviewed)
            if evaluate_clicked:
                metrics = evaluate_run(run_dir, result, config)
                st.session_state["lab_current_metrics"] = metrics
            else:
                st.session_state.pop("lab_current_metrics", None)
                stale_eval = run_dir/"evaluation.json"
                if stale_eval.exists():
                    stale_eval.unlink()
            st.success(f"Saved review.json and {len(rows)} ground-truth interval(s)." if gt_path else
                       "Saved review.json. No reviewed ground-truth intervals yet.")
        except (OSError, ValueError, FileNotFoundError) as exc:
            st.error(str(exc))
    gt_path = run_dir/"ground_truth.csv"
    if gt_path.is_file():
        st.download_button("Download ground_truth.csv", gt_path.read_bytes(),
                           file_name=f"{run_dir.name}_ground_truth.csv", mime="text/csv",
                           key=f"lab_download_gt_{run_dir.name}")
    metrics = st.session_state.get("lab_current_metrics")
    if metrics is None and (run_dir/"evaluation.json").is_file():
        metrics = json.loads((run_dir/"evaluation.json").read_text(encoding="utf-8"))
    if metrics is not None:
        _evaluation_metrics(metrics)
    elif not gt_path.exists():
        st.info("Save at least one human-labeled interval to make evaluation available.")


def _optimization(run_dir: Path, result: dict, config: dict) -> None:
    st.subheader("6 · Optimize VAD")
    st.caption("Uses saved human labels and cached Silero probabilities. Results are development candidates for this Duet.")
    if st.button("Optimize VAD", disabled=not (run_dir/"ground_truth.csv").is_file(),
                 key=f"lab_optimize_{run_dir.name}"):
        with st.spinner("Searching VAD settings from cached probabilities…"):
            try:
                report = optimize_vad(run_dir, result, config,
                    review_metadata(run_dir)["full_video_reviewed_for_missed_speech"])
            except (OSError, ValueError, RuntimeError) as exc:
                st.error(str(exc))
            else:
                st.session_state[f"lab_optimization_{run_dir.name}"] = report
                st.success(f"Measured {report['candidate_count']} candidate settings. Saved JSON and CSV.")
    report = st.session_state.get(f"lab_optimization_{run_dir.name}")
    if report is None and (run_dir/"vad_optimization.json").exists():
        report = json.loads((run_dir/"vad_optimization.json").read_text(encoding="utf-8"))
    if report is None:
        return
    st.warning(report["validation_scope"])
    st.caption(report.get("limitations", ""))
    if not report.get("development_targets_met", False):
        st.warning("No VAD-only candidate met both recall and Original-contamination targets on saved labels. Inspect the leakage filter separately.")
    baseline, best = report["baseline"], report["best_development_candidate"]
    st.dataframe(pd.DataFrame([
        {"Setting": "Current baseline", **baseline["parameters"], "F1": baseline["learner_f1"],
         "Recall": baseline["learner_recall"], "Contamination": baseline["original_contamination_rate"]},
        {"Setting": "Best development", **best["parameters"], "F1": best["learner_f1"],
         "Recall": best["learner_recall"], "Contamination": best["original_contamination_rate"]},
    ]), hide_index=True, width="stretch")
    st.dataframe(pd.DataFrame([{**row["parameters"], "F1": row["learner_f1"],
        "Recall": row["learner_recall"], "Contamination": row["original_contamination_rate"],
        "Boundary error": row["median_boundary_error_sec"], "Segments": row["fragmentation_count"]}
        for row in report["top_candidates"]]), hide_index=True, width="stretch")
    with st.expander("Pareto-like candidates · tradeoffs", expanded=False):
        st.dataframe(pd.DataFrame([{**row["parameters"], "F1": row["learner_f1"],
            "Recall": row["learner_recall"], "Contamination": row["original_contamination_rate"],
            "Boundary error": row["median_boundary_error_sec"], "Segments": row["fragmentation_count"]}
            for row in report.get("pareto_candidates", [])]), hide_index=True, width="stretch")
    if st.button("Preview Candidate", key=f"lab_preview_button_{run_dir.name}"):
        candidate_cfg = copy.deepcopy(config)
        candidate_cfg["vad"].update({k:v for k,v in best["parameters"].items() if k != "merge_gap_sec"})
        candidate_cfg["segments"]["merge_gap_sec"] = best["parameters"]["merge_gap_sec"]
        preview = predict_candidate(run_dir, result, candidate_cfg)
        st.session_state[f"lab_preview_{run_dir.name}"] = preview
    preview = st.session_state.get(f"lab_preview_{run_dir.name}")
    if preview:
        candidate_result = dict(result) | preview
        st.plotly_chart(timeline_figure(candidate_result), width="stretch", theme=None,
                        key=f"lab_candidate_timeline_{run_dir.name}")
        st.caption(f"Preview: {len(preview['learner_segments'])} learner segments, "
                   f"{len(preview['reference_leakage_candidates'])} leakage candidates filtered.")
    apply, keep = st.columns(2)
    if apply.button("Apply Candidate · create new run", key=f"lab_apply_{run_dir.name}"):
        candidate_cfg = copy.deepcopy(config)
        candidate_cfg["vad"].update({k:v for k,v in best["parameters"].items() if k != "merge_gap_sec"})
        candidate_cfg["segments"]["merge_gap_sec"] = best["parameters"]["merge_gap_sec"]
        source_original = next((run_dir/"inputs").glob("original.*"))
        source_duet = next((run_dir/"inputs").glob("duet.*"))
        with st.spinner("Creating new candidate run…"):
            new_dir, _ = execute_analysis(source_original, source_duet, candidate_cfg, RUNS)
        st.session_state["lab_active_run"] = str(new_dir)
        st.session_state.pop("lab_loaded_review_run", None)
        st.rerun()
    if keep.button("Keep Current", key=f"lab_keep_{run_dir.name}"):
        st.session_state.pop(f"lab_preview_{run_dir.name}", None)
        st.info("Current run and settings retained.")


def _diagnostics(run_dir: Path, result: dict, config: dict) -> None:
    with st.expander("Advanced / Diagnostics", expanded=False):
        align = result["alignment_diagnostics"]
        cancel = result.get("cancellation_diagnostics") or {}
        st.write(f"Coarse offset: {align.get('coarse_offset_sec')} s · fine b: {align.get('b')} s · "
                 f"time scale a: {align.get('a')}")
        st.write(f"Reference suppression: {cancel.get('reference_suppression_db', 'not measured')} dB · "
                 f"backend: {cancel.get('backend', 'not measured')}")
        comparison = result.get("backend_comparison")
        if comparison:
            st.markdown("**AUTO backend comparison**")
            st.write(comparison["selection_rule"])
            st.dataframe(pd.DataFrame(comparison["candidates"]), hide_index=True, width="stretch")
        if result.get("leakage_diagnostics"):
            st.markdown("**Per-segment reference leakage diagnostics**")
            st.dataframe(pd.DataFrame(result["leakage_diagnostics"]), hide_index=True, width="stretch")
        for warning in result.get("warnings", []):
            st.warning(warning)
        st.markdown("**Alignment anchors**")
        st.dataframe(pd.DataFrame(align.get("anchors", [])), hide_index=True, width="stretch")
        st.markdown("**VAD configuration used for this run**")
        st.json(result.get("vad_configuration", {}))
        st.markdown("**Exact saved configuration**")
        st.json(config)
        for name in ("debug_alignment.png", "debug_timeline.png"):
            path = run_dir/name
            if path.is_file():
                st.image(str(path), caption=name, width="stretch")
        residual = run_dir/"residual_detection.wav"
        if residual.is_file():
            st.markdown("**residual_detection.wav — diagnostic audio only. Never use for pronunciation scoring.**")
            st.audio(str(residual))
        st.markdown("**Raw result.json**")
        st.code((run_dir/"result.json").read_text(encoding="utf-8"), language="json")


def _cohort_dashboard(config: dict) -> None:
    st.subheader("P1.4 · Cohort triage and scorability")
    template = Path(st.text_input("Template video", str(ROOT/"data"/"templates"/"T001"/"original.mp4"))).expanduser()
    duet_dir = Path(st.text_input("Duet folder", str(ROOT/"data"/"duets"/"T001"))).expanduser()
    output = COHORT_RUNS/"T001_p14"
    count = len([p for p in duet_dir.glob("*") if p.suffix.lower() in {".mp4", ".mov", ".mkv"}]) if duet_dir.is_dir() else 0
    st.caption(f"Detected {count} Duet files · pseudonymous report IDs T001-D001… · output: {output}")
    build_col, run_col = st.columns(2)
    if build_col.button("Build / Load Template Profile", disabled=not template.is_file(), width="stretch"):
        try:
            with st.spinner("Preparing reusable template profile…"):
                profile = build_template_profile(template, output/"template_profile", "T001", config)
            st.success(f"Profile ready: {profile.template_id} · {profile.profile['anchor_count']} visual anchors")
        except (OSError, RuntimeError, ValueError) as exc:
            st.error(str(exc))
    if run_col.button("Run Batch Pre-scan", disabled=not template.is_file() or count == 0,
                      type="primary", width="stretch"):
        progress = st.progress(0, text="Starting cohort")
        def update(index: int, total: int, pair_id: str) -> None:
            progress.progress(index/total, text=f"{pair_id} · {index}/{total}")
        try:
            result = run_cohort(template, duet_dir, output, "T001", config, progress_callback=update)
            st.success(f"Processed {len(result['rows'])} Duets. Results saved in {output}")
        except (OSError, RuntimeError, ValueError) as exc:
            st.error(str(exc))
    summary_path = next((output/name for name in ("cohort_summary_v3.json", "cohort_summary_v2.json",
                                                  "cohort_summary.json") if (output/name).is_file()), output/"cohort_summary.json")
    manifest_path = next((output/name for name in ("development_manifest_v3.json", "development_manifest_v2.json",
                                                   "cohort_manifest.json") if (output/name).is_file()), output/"cohort_manifest.json")
    if not summary_path.is_file() or not manifest_path.is_file():
        st.info("Build the profile and run Batch Pre-scan to populate the cohort dashboard.")
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    quality, score, audio, backend = (summary["quality_gate_distribution"],
        summary["scorability_distribution"], summary["audio_state_distribution"],
        summary["backend_distribution"])
    cards = [("TOTAL DUETS", summary["total_duets"]), ("GREEN", quality.get("GREEN", 0)),
        ("AMBER", quality.get("AMBER", 0)), ("RED", quality.get("RED", 0)),
        ("SCORABLE CLEAN", score.get("SCORABLE_CLEAN", 0)),
        ("SCORABLE AFTER CANCELLATION", score.get("SCORABLE_AFTER_CANCELLATION", 0)),
        ("UNSCORABLE OVERLAP", score.get("UNSCORABLE_REFERENCE_OVERLAP", 0)),
        ("ALIGNMENT FAILURE", score.get("UNSCORABLE_ALIGNMENT", 0)),
        ("MUTED", audio.get("CLEAN_MUTED", 0)), ("REFERENCE PRESENT", audio.get("REFERENCE_PRESENT", 0)),
        ("UNCERTAIN", audio.get("REFERENCE_PRESENCE_UNCERTAIN", 0)),
        ("HUMAN REVIEW", summary["human_review_required_videos"])]
    for start in range(0, len(cards), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, cards[start:start+4]):
            column.metric(label, value)
    st.caption(f"Backends: NONE {backend.get('NONE', 0)} · LINEAR {backend.get('LINEAR', 0)} · "
               f"AEC3 {backend.get('AEC3', 0)} · review reduction estimate "
               f"{summary['estimated_video_review_reduction']:.1%}")
    if summary.get("version") in {"P1.4b-v2", "P1.4c-v3"}:
        st.info(f"{summary['version']} development-only view. The version-2 holdout is excluded from this dashboard.")
    st.warning("Triage and quality gates are engineering predictions until calibration labels and the Green audit are completed.")
    view = st.selectbox("Suspicious view", ["All", "Highest template-audio presence", "Worst cancellation",
        "Lowest visual alignment", "Most leakage candidates", "Most overlap candidates", "Most fragmented",
        "Longest learner speech", "Shortest learner speech"])
    frame = pd.DataFrame(rows)
    ordering = {"Highest template-audio presence": ("reference_audio_presence_score", False),
        "Worst cancellation": ("reference_suppression_db", True), "Lowest visual alignment": ("visual_match_score", True),
        "Most leakage candidates": ("leakage_candidate_count", False),
        "Most overlap candidates": ("overlap_candidate_count", False), "Most fragmented": ("interval_count", False),
        "Longest learner speech": ("learner_duration_sec", False), "Shortest learner speech": ("learner_duration_sec", True)}
    if view in ordering:
        key, ascending = ordering[view]
        frame = frame.sort_values(key, ascending=ascending, na_position="last")
    display_columns = ["pair_id", "visual_match_score", "reference_audio_presence_score", "audio_state",
        "selected_cancellation_backend", "reference_suppression_db", "scorability_status", "quality_gate",
        "learner_duration_sec", "interval_count", "warning_count"]
    event = st.dataframe(frame[display_columns], hide_index=True, width="stretch", height=420,
                         on_select="rerun", selection_mode="single-row", key="cohort_table")
    selected_indices = event.selection.rows if hasattr(event, "selection") else []
    selected_pair = frame.iloc[selected_indices[0]]["pair_id"] if selected_indices else st.selectbox(
        "Inspect pair", frame["pair_id"].tolist())
    pair_dir = output/"pairs"/selected_pair
    pair_result_path = pair_dir/"result.json"
    if pair_result_path.is_file():
        result = json.loads(pair_result_path.read_text(encoding="utf-8"))
        selected_row = frame.loc[frame["pair_id"] == selected_pair].iloc[0].to_dict()
        for key in ("audio_state", "reference_audio_presence_score", "scorability_status",
                    "scorability_reasons", "quality_gate", "quality_gate_reasons",
                    "background_interference", "low_speech_level", "reference_contamination_scope"):
            if key in selected_row:
                result[key] = selected_row[key]
        v2_presence = pair_dir/"reference_audio_presence_v2.json"
        v2_quality = pair_dir/"audio_quality_v2.json"
        v3_quality = pair_dir/"audio_quality_v3.json"
        if v2_presence.is_file():
            result.update(json.loads(v2_presence.read_text(encoding="utf-8")))
        if v2_quality.is_file():
            result["audio_quality_v2"] = json.loads(v2_quality.read_text(encoding="utf-8"))
        if summary.get("version") == "P1.4c-v3" and v3_quality.is_file():
            result["audio_quality_v3"] = json.loads(v3_quality.read_text(encoding="utf-8"))
        st.markdown(f"**{selected_pair} · {result['audio_state']} · {result['scorability_status']} · {result['quality_gate']}**")
        left, right = st.columns(2)
        left.json({"visual_alignment": result["visual_alignment"],
                   "audio_presence": result["reference_audio_presence_features"]})
        right.json({"selected_audio_path": result["selected_audio_path"],
                    "backend": result["selected_cancellation_backend"],
                    "scorability_reasons": result["scorability_reasons"],
                    "quality_gate_reasons": result["quality_gate_reasons"], "warnings": result["warnings"]})
        st.dataframe(pd.DataFrame(result.get("suspicious_intervals", [])), hide_index=True, width="stretch")
        st.video(result["duet_path"])
        audio_columns = st.columns(3)
        if (pair_dir/"duet_normalized.wav").is_file():
            audio_columns[0].caption("Raw normalized Duet")
            audio_columns[0].audio(str(pair_dir/"duet_normalized.wav"))
        if (pair_dir/"residual_detection.wav").is_file():
            audio_columns[1].caption("Selected detection path")
            audio_columns[1].audio(str(pair_dir/"residual_detection.wav"))
        reference = output/"template_profile"/"normalized_reference.wav"
        if reference.is_file():
            audio_columns[2].caption("Template reference")
            audio_columns[2].audio(str(reference))
    calibration_path = output/"calibration_labels.json"
    if calibration_path.is_file():
        with st.expander("Minimal audio-state calibration · 6–10 representative videos"):
            payload = json.loads(calibration_path.read_text(encoding="utf-8"))
            edited = st.data_editor(pd.DataFrame(payload["labels"]), hide_index=True, width="stretch",
                column_config={"human_label": st.column_config.SelectboxColumn("Human label",
                    options=["UNREVIEWED", "TEMPLATE_AUDIO_MUTED", "TEMPLATE_AUDIO_PRESENT", "UNCERTAIN"])} )
            if st.button("Save calibration labels"):
                payload["labels"] = json.loads(edited.to_json(orient="records"))
                payload["status"] = "COMPLETE" if all(x["human_label"] != "UNREVIEWED" for x in payload["labels"]) else "PARTIAL"
                calibration_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
                st.success("Calibration labels saved separately from predictions.")
    audit_path = next((output/name for name in ("green_audit_v3.json", "green_audit_v2.json",
                                                 "green_audit.json") if (output/name).is_file()), output/"green_audit.json")
    if audit_path.is_file():
        with st.expander("Deterministic Green audit"):
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            edited = st.data_editor(pd.DataFrame(audit["items"]), hide_index=True, width="stretch",
                column_config={"audit": st.column_config.SelectboxColumn("Audit", options=["UNREVIEWED", "PASS", "FAIL"])})
            if st.button("Save Green audit"):
                audit["items"] = json.loads(edited.to_json(orient="records"))
                audit.update(audit_outcome(audit))
                audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
                summary["green_audit"].update(audit_outcome(audit))
                if "artifacts_sha256" in summary:
                    summary["artifacts_sha256"][audit_path.name] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
                summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
                st.success("Green audit saved; validated." if audit["validated"] else "Green audit saved; gate remains unvalidated.")


st.markdown("<div class='lab-kicker'>Phase 1 · Research Console v0.2</div>", unsafe_allow_html=True)
st.title("Duet Speech Lab")
st.markdown("<div class='lab-subtitle'>Run the reference-aware segmenter, inspect learner timestamps, "
            "listen to the original Duet audio, and build human ground truth.</div>", unsafe_allow_html=True)

def _phase2_evidence_dashboard() -> None:
    """Read-only view of saved development evidence; never runs a model."""
    output = ROOT / "assessment_runs" / "T001_p2"
    summary_path = output / "cohort_summary.json"
    st.subheader("Phase 2.1 · Speaking evidence")
    st.caption("Measurements for research review only. No English proficiency score is produced.")
    if not summary_path.is_file():
        st.info("No saved Phase 2.1 development sample yet.")
        return
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        pair_ids = [item["pair_id"] for item in summary["sample"]]
        selected = st.selectbox("Saved development video", pair_ids)
        evidence = json.loads((output / "pairs" / selected / "evidence.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Could not read saved evidence: {exc}")
        return
    st.info("GREEN allows evidence extraction. It does not mean the student passed an English test.")
    if evidence["task_profile"]["mode"] == "AUTO_TURN_FALLBACK":
        st.warning("Turn boundaries are automatic estimates. Verify them before interpreting measurements.")
    aggregate = evidence["aggregate_fluency_evidence"]
    columns = st.columns(4)
    columns[0].metric("Recognized words", aggregate["word_count"])
    columns[1].metric("Speech rate (words/min)", aggregate["speech_rate_wpm"])
    columns[2].metric("Pause time (%)", round(100 * aggregate["pause_ratio"], 1))
    columns[3].metric("Longest pause (sec)", aggregate["longest_pause_sec"])
    for turn in evidence["turns"]:
        st.markdown(f"**{turn['turn_id']} · {turn['start_sec']:.1f}–{turn['end_sec']:.1f} s**")
        audio_path = output / turn["model_input_ref"]
        if audio_path.is_file():
            st.audio(str(audio_path))
        st.write(turn["transcript"]["verbatim_transcript"] or "(No words recognized)")
        with st.expander("Word timestamps and detailed measurements"):
            st.dataframe(pd.DataFrame(turn["transcript"]["words"]), hide_index=True, width="stretch")
            st.json({"fluency": turn["fluency"], "acoustic": turn["acoustic"]})
    with st.expander("Source and limits"):
        st.json({"audio_provenance": evidence["audio_provenance"],
                 "asr_provenance": evidence["asr_provenance"],
                 "warnings": evidence["warnings"], "limitations": evidence["limitations"]})


def _p21b_validation_dashboard() -> None:
    """One-time human task-structure confirmation and three-video ASR audit."""
    import plotly.graph_objects as go
    from speaking_evidence.p21b import (AUDIT_IDS, compare_models, confirm_profile,
                                        evaluate_model, run_confirmed, save_human_reference)
    from speaking_evidence.runner import write_json

    candidate_path = ROOT / "task_profiles" / "T001_v1_candidate.json"
    confirmed_path = ROOT / "task_profiles" / "T001_v1.json"
    template_path = ROOT / "data" / "templates" / "T001" / "original.mp4"
    cohort_dir = ROOT / "cohort_runs" / "T001_p14"
    output_dir = ROOT / "assessment_runs" / "T001_p21b"
    st.subheader("P2.1b · Kiểm tra cấu trúc bài nói T001")
    st.caption("Chỉ xác nhận phần nào là lượt trả lời. Chưa chấm tiếng Anh của học sinh.")
    if not candidate_path.is_file():
        st.error("Chưa có vùng trả lời đề xuất. Chạy: python -m speaking_evidence.p21b propose")
        return
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    st.info("Máy đề xuất 1 vùng trả lời dựa trên 9 video GREEN tập phát triển. Đây là bản nháp; hãy xem template một lần và sửa nếu cần.")
    st.video(str(template_path))
    reference_vad = json.loads((cohort_dir / "template_profile" / "reference_vad.json").read_text(encoding="utf-8"))
    figure = go.Figure()
    for span in reference_vad:
        figure.add_trace(go.Scatter(x=[span["start"], span["end"]], y=["Tiếng mẫu", "Tiếng mẫu"],
                                    mode="lines", line=dict(color="#94a3b8", width=12), showlegend=False))
    shown_turns = (json.loads(confirmed_path.read_text(encoding="utf-8"))["turns"]
                   if confirmed_path.is_file() else candidate["turns"])
    for turn in shown_turns:
        figure.add_trace(go.Scatter(x=[turn["start_sec"], turn["end_sec"]],
                                    y=["Vùng học sinh trả lời", "Vùng học sinh trả lời"],
                                    mode="lines", line=dict(color="#0f766e", width=16),
                                    name=turn["turn_id"], showlegend=True))
    figure.update_layout(height=220, xaxis_title="Giây trên template T001",
                         xaxis_range=[0, candidate["template_duration_sec"]], margin=dict(l=20, r=20, t=20, b=25))
    st.plotly_chart(figure, width="stretch")
    if confirmed_path.is_file():
        st.success("Cấu trúc bài T001 đã được người nghiên cứu xác nhận và lưu riêng.")
        st.dataframe(pd.DataFrame(shown_turns), hide_index=True, width="stretch")
    else:
        st.write("Sửa mốc bắt đầu/kết thúc, thêm hoặc xóa lượt nếu template thực sự có nhiều lượt trả lời. Có thể để trống câu hỏi và bài đọc mẫu.")
        edited = st.data_editor(pd.DataFrame(candidate["turns"])[
            ["turn_id", "start_sec", "end_sec", "mode", "prompt_text", "target_text"]],
            hide_index=True, num_rows="dynamic", width="stretch", key="p21b_task_editor",
            column_config={"mode": st.column_config.SelectboxColumn(
                "Loại lượt", options=["UNKNOWN", "OPEN_RESPONSE", "CONTROLLED_READING"]),
                "start_sec": st.column_config.NumberColumn("Bắt đầu (giây)", min_value=0.0, step=0.1),
                "end_sec": st.column_config.NumberColumn("Kết thúc (giây)", min_value=0.1, step=0.1)})
        checked = st.checkbox("Tôi đã xem template và xác nhận các vùng trả lời bên trên", key="p21b_human_confirm")
        if st.button("Lưu TaskProfile đã xác nhận", disabled=not checked):
            try:
                turns = []
                for row in edited.to_dict(orient="records"):
                    turns.append({"turn_id": str(row["turn_id"]).strip(),
                                  "start_sec": float(row["start_sec"]), "end_sec": float(row["end_sec"]),
                                  "mode": str(row["mode"]),
                                  "prompt_text": "" if pd.isna(row["prompt_text"]) else str(row["prompt_text"]),
                                  "target_text": "" if pd.isna(row["target_text"]) else str(row["target_text"]),
                                  "scoring_dimensions": []})
                confirm_profile(candidate, turns, template_path, confirmed_path, confirmed=checked)
                st.success("Đã lưu xác nhận. Đang tạo lại bằng chứng cho 5 video mẫu…")
                with st.spinner("Xử lý 5 video GREEN; có thể mất vài phút"):
                    run_confirmed(cohort_dir, confirmed_path, ROOT / "assessment_runs" / "T001_p2",
                                  output_dir, ROOT / "p2_config.yaml")
                st.rerun()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                st.error(f"Chưa thể lưu/chạy: {exc}")
        return
    summary_path = output_dir / "sample_summary.json"
    if not summary_path.is_file():
        st.warning("TaskProfile đã xác nhận nhưng 5 video chưa xử lý xong.")
        if st.button("Chạy lại 5 video GREEN bằng TaskProfile"):
            with st.spinner("Đang xử lý 5 video mẫu"):
                run_confirmed(cohort_dir, confirmed_path, ROOT / "assessment_runs" / "T001_p2",
                              output_dir, ROOT / "p2_config.yaml")
            st.rerun()
        return
    st.subheader("So sánh số đo trước và sau khi xác nhận lượt nói")
    comparisons = json.loads((output_dir / "old_vs_new.json").read_text(encoding="utf-8"))
    st.dataframe(pd.DataFrame(comparisons), hide_index=True, width="stretch")
    st.caption("Đây là thay đổi cách chia lượt và số đo, không phải thay đổi năng lực tiếng Anh.")
    st.subheader("Kiểm tra bản chép lời · 3 video")
    st.write("Nghe âm thanh từng lượt và sửa lời máy nghe sai. Giữ nguyên những gì học sinh thực sự nói, kể cả chỗ lặp hoặc sai ngữ pháp.")
    pair_id = st.selectbox("Video cần kiểm tra", list(AUDIT_IDS), key="p21b_audit_pair")
    audit_dir = output_dir / "asr_validation" / pair_id
    asr = json.loads((audit_dir / "asr_transcript.json").read_text(encoding="utf-8"))
    reference = json.loads((audit_dir / "human_reference.json").read_text(encoding="utf-8"))
    reference_by_turn = {t["turn_id"]: t["reference_text"] for t in reference["turns"]}
    texts = {}
    for turn in asr["turns"]:
        st.markdown(f"**{turn['turn_id']} · {turn['start_sec']:.1f}–{turn['end_sec']:.1f} giây**")
        st.audio(str(output_dir / turn["model_input_ref"]))
        st.caption("Máy chép: " + (turn["transcript"]["verbatim_transcript"] or "(trống)"))
        saved = reference_by_turn[turn["turn_id"]]
        texts[turn["turn_id"]] = st.text_area("Bạn nghe được", value=saved if saved is not None else
            turn["transcript"]["verbatim_transcript"], key=f"p21b_ref_{pair_id}_{turn['turn_id']}")
    confirmed_audit = st.checkbox("Tôi đã nghe và sửa xong video này", key=f"p21b_ref_confirm_{pair_id}")
    if st.button("Lưu bản nghe của tôi", disabled=not confirmed_audit):
        saved = save_human_reference(output_dir, pair_id, texts, confirmed_audit)
        metrics = evaluate_model(asr, saved)
        write_json(audit_dir / "small_metrics.json", metrics)
        st.success(f"Đã lưu. Sai số chép lời small.en (WER): {metrics['wer']:.1%}" if metrics["wer"] is not None
                   else "Đã lưu; không thể tính WER vì bản tham chiếu không có từ.")
    all_reviewed = all(json.loads((output_dir / "asr_validation" / pid / "human_reference.json").read_text(
        encoding="utf-8")).get("human_confirmed") for pid in AUDIT_IDS)
    if all_reviewed:
        st.success("Đã có đủ 3 bản nghe của người nghiên cứu.")
        if st.button("So sánh small.en và medium.en trên đúng 3 video này"):
            with st.spinner("Đang chạy medium.en trên 3 video; lần đầu có thể cần tải mô hình"):
                compare_models(output_dir, ROOT / "p2_config.yaml")
            st.rerun()
    comparison_path = output_dir / "model_comparison.json"
    if comparison_path.is_file():
        st.json(json.loads(comparison_path.read_text(encoding="utf-8")))


def _p22a_dashboard() -> None:
    """Minimal human-ground-truth workflow for controlled-reading calibration."""
    from speaking_evidence.p22 import (ASR_AUDIT_IDS, DISCLAIMER, calibrate, calibration_readiness,
        compare_asr_models, confirm_target, generate_selected_evidence, save_asr_reference, save_rating)

    target_path = ROOT / "task_profiles" / "T001_target_text_v1.json"
    ground = ROOT / "human_ground_truth" / "p22a_v1"
    evidence = ROOT / "assessment_runs" / "T001_p22_calibrated_v01"
    calibration = ROOT / "calibration" / "p22a_v01"
    st.subheader("P2.2A · Ground truth and calibration")
    st.warning("DEVELOPMENT / PRELIMINARY CALIBRATION · NOT CEFR · NOT B2 · NOT IELTS")
    target_tab, asr_tab, ratings_tab, result_tab = st.tabs(
        ["1 · Văn bản mẫu", "2 · Sửa 6 bản chép lời", "3 · Chấm 12 video", "4 · Hiệu chỉnh"])
    with target_tab:
        target = json.loads(target_path.read_text(encoding="utf-8"))
        st.video(str(ROOT / "data" / "templates" / "T001" / "original.mp4"))
        st.caption("Hai mô hình small.en và medium.en cho cùng một bản nháp 142 từ từ âm thanh template. Hãy đối chiếu một lần; không thêm từ không có trong bài.")
        text_value = target["confirmed_text"] if target["human_confirmed"] else target["machine_candidate"]
        edited_target = st.text_area("Văn bản đọc mẫu", value=text_value, height=260,
                                     disabled=target["human_confirmed"], key="p22_target_text")
        if target["human_confirmed"]:
            st.success("Văn bản mẫu đã được người nghiên cứu xác nhận.")
        else:
            target_check = st.checkbox("Tôi đã nghe/xem template và xác nhận văn bản này",
                                       key="p22_target_confirm")
            if st.button("Lưu văn bản mẫu đã xác nhận", disabled=not target_check):
                confirm_target(target, edited_target, target_path)
                st.rerun()
        with st.expander("Nguồn và dấu vết"):
            st.json({k: target[k] for k in ("template_sha256", "source", "human_confirmed", "status")})
    with asr_tab:
        queue = json.loads((ground / "asr_reference_v1" / "queue.json").read_text(encoding="utf-8"))
        reviewed = []
        for pair in ASR_AUDIT_IDS:
            record = json.loads((ground / "asr_reference_v1" / pair / "reference.json").read_text(encoding="utf-8"))
            if record["human_confirmed"]:
                reviewed.append(pair)
        st.progress(len(reviewed) / len(ASR_AUDIT_IDS), text=f"Đã sửa {len(reviewed)}/6 video")
        pair_id = st.selectbox("Video", list(ASR_AUDIT_IDS), key="p22_asr_pair")
        path = ground / "asr_reference_v1" / pair_id / "reference.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        audio_path = evidence / record["model_input_ref"]
        st.audio(str(audio_path))
        st.caption("Bản máy nghe ban đầu: " + record["original_asr"]["verbatim_transcript"])
        value = record["human_verbatim_text"] if record["human_confirmed"] else record["original_asr"]["verbatim_transcript"]
        corrected = st.text_area("Sửa đúng những gì học sinh thực sự nói", value=value, height=220,
                                 key=f"p22_asr_text_{pair_id}")
        st.caption("Giữ nguyên chỗ lặp, bỏ dở hoặc sai ngữ pháp. Chỉ sửa lỗi máy nghe.")
        ref_check = st.checkbox("Tôi đã nghe hết và sửa xong video này", key=f"p22_asr_check_{pair_id}")
        if st.button("Lưu bản nghe của người", disabled=not ref_check, key=f"p22_asr_save_{pair_id}"):
            save_asr_reference(path, corrected, ref_check)
            st.rerun()
        if len(reviewed) == len(ASR_AUDIT_IDS):
            st.success("Đã đủ 6 bản tham chiếu của người.")
            selection_path = calibration / "asr_model_selection_v1.json"
            if not selection_path.is_file() and st.button("Đo WER small.en và medium.en trên cùng 6 audio"):
                with st.spinner("Đang chạy medium.en; có thể mất vài phút"):
                    compare_asr_models(ground, evidence, ROOT / "p2_config.yaml", calibration)
                st.rerun()
            if selection_path.is_file():
                selection = json.loads(selection_path.read_text(encoding="utf-8"))
                st.json(selection)
                evidence_summary = evidence / "selected_backend_evidence_summary.json"
                if not evidence_summary.is_file() and st.button("Tạo bằng chứng cho 12 video bằng mô hình đã chọn"):
                    with st.spinner("Đang xử lý 12 video phát triển"):
                        generate_selected_evidence(ground, evidence, ROOT / "p2_config.yaml", calibration)
                    st.rerun()
    with ratings_tab:
        ratings_path = ground / "ratings_v2.json" if (ground / "ratings_v2.json").is_file() else ground / "ratings_v1.json"
        payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        completed = [x for x in payload["items"] if x["human_confirmed"]]
        st.progress(len(completed) / len(payload["items"]), text=f"Đã xử lý {len(completed)}/12 video")
        st.markdown("**Thang dùng chung:** 1 = vấn đề nghiêm trọng; 3 = trung bình; 5 = rất rõ và ổn định.")
        st.markdown("- **Fluency:** độ liền mạch, ngập ngừng, lặp/sửa và dòng chảy; không chấm phát âm.\n- **Pronunciation:** độ chính xác/rõ của từ và âm; không trừ điểm chỉ vì giọng Việt.\n- **Intelligibility:** mức dễ hiểu khi không nhìn transcript.\n- **Prosody:** nhịp, chia cụm, trọng âm và ngữ điệu; không lặp lại Fluency.\n\nKhông chấm ngữ pháp hoặc từ vựng.")
        pair_id = st.selectbox("Video cần chấm", [x["pair_id"] for x in payload["items"]], key="p22_rating_pair")
        item = next(x for x in payload["items"] if x["pair_id"] == pair_id)
        raw = json.loads((evidence / "pairs" / pair_id / "raw_evidence.json").read_text(encoding="utf-8"))
        st.video(raw["raw_duet_path"])
        st.audio(str(evidence / raw["model_input_ref"]))
        if item["quality_gate"] == "AMBER":
            st.warning("Video AMBER: trước hết hãy quyết định âm thanh có đủ để chấm hay không.")
            default = item["amber_scorability"] if item["amber_scorability"] in {"SCORABLE", "NOT_SCORABLE"} else "PENDING"
            scorability = st.radio("Khả năng chấm", ["PENDING", "SCORABLE", "NOT_SCORABLE"],
                                   index=["PENDING", "SCORABLE", "NOT_SCORABLE"].index(default), horizontal=True,
                                   key=f"p22_scorable_{pair_id}")
        else:
            scorability = "SCORABLE"
        scores = {}
        if scorability != "NOT_SCORABLE":
            for name, label in (("fluency", "Fluency"), ("pronunciation", "Pronunciation"),
                                ("intelligibility", "Intelligibility"), ("prosody", "Prosody")):
                scores[name] = st.slider(label, 1, 5, int(item[name] or 3), key=f"p22_{name}_{pair_id}")
        pronunciation_examples = st.text_input("Pronunciation examples / problematic words (không bắt buộc)",
                                               value=item.get("pronunciation_examples", ""),
                                               key=f"p22_pronunciation_examples_{pair_id}")
        note = st.text_input("Ghi chú ngắn (không bắt buộc)", value=item["note"], key=f"p22_note_{pair_id}")
        rating_check = st.checkbox("Tôi đã nghe/xem và xác nhận lựa chọn này", key=f"p22_rating_check_{pair_id}")
        blocked = not rating_check or (item["quality_gate"] == "AMBER" and scorability == "PENDING")
        if st.button("Lưu đánh giá", disabled=blocked, key=f"p22_rating_save_{pair_id}"):
            save_rating(ratings_path, pair_id, scorability, scores, note, rating_check,
                        pronunciation_examples=pronunciation_examples)
            st.rerun()
    with result_tab:
        target = json.loads(target_path.read_text(encoding="utf-8"))
        ratings_path = ground / "ratings_v2.json" if (ground / "ratings_v2.json").is_file() else ground / "ratings_v1.json"
        ratings = json.loads(ratings_path.read_text(encoding="utf-8"))["items"]
        usable = [x for x in ratings if x["human_confirmed"] and x["amber_scorability"] != "NOT_SCORABLE"]
        readiness = calibration_readiness(ratings)
        evidence_ready = (evidence / "selected_backend_evidence_summary.json").is_file()
        st.write(f"Nhãn chấm được: {len(usable)} · Văn bản mẫu xác nhận: {target['human_confirmed']} · ASR đã chọn: {evidence_ready}")
        if readiness["status"] != "READY_FOR_DEVELOPMENT_CALIBRATION":
            st.info("WAITING FOR HUMAN CALIBRATION")
            for reason in readiness["reasons"]:
                st.caption(reason)
        ready = (readiness["status"] == "READY_FOR_DEVELOPMENT_CALIBRATION"
                 and target["human_confirmed"] and evidence_ready)
        if st.button("Tạo hiệu chỉnh phát triển v0.1", disabled=not ready):
            result = calibrate(ground, evidence, target_path, calibration, evidence)
            st.json(result)
        result_path = evidence / "calibration_summary.json"
        if result_path.is_file():
            st.json(json.loads(result_path.read_text(encoding="utf-8")))
        else:
            st.caption("Chưa có điểm. Prosody sẽ đứng riêng; Overall chỉ xuất hiện khi các ánh xạ bắt buộc đủ căn cứ.")


def _teacher_rating_dashboard() -> None:
    """Focused, machine-score-blind teacher workflow with persistent JSON saves."""
    from speaking_evidence.p22 import save_rating

    ground = ROOT / "human_ground_truth" / "p22a_v1"
    evidence = ROOT / "assessment_runs" / "T001_p22_calibrated_v01"
    ratings_path = ground / "ratings_v2.json" if (ground / "ratings_v2.json").is_file() else ground / "ratings_v1.json"
    st.title("Teacher Rating — P2.2A")
    if not ratings_path.is_file():
        st.error("Chưa có hàng chờ 12 video.")
        return
    payload = json.loads(ratings_path.read_text(encoding="utf-8"))
    items = payload["items"]
    completed = [item for item in items if item.get("human_confirmed")]
    st.progress(len(completed) / len(items), text=f"Tiến độ: {len(completed)} / {len(items)}")
    st.caption("Chấm phần học sinh nói. 1 = rất yếu, 3 = trung bình, 5 = rất tốt. Không chấm ngữ pháp hay từ vựng.")
    with st.expander("Hướng dẫn 4 tiêu chí", expanded=True):
        st.markdown("""
**Fluency — How smoothly and continuously does the learner speak?**

Nghe khoảng dừng, ngập ngừng, lặp/sửa và độ liền mạch. Không chấm phát âm ở đây.

**Pronunciation — How accurately and clearly are the English words and sounds produced?**

Nghe phụ âm/nguyên âm, âm cuối, âm bị bỏ/sai, cách đọc từ và word stress rõ ràng. Không trừ điểm chỉ vì giọng Việt. 1 = nhiều từ khó nhận ra; 3 = nhìn chung hiểu nhưng lỗi lặp lại; 5 = rõ và chính xác nhất quán.

**Intelligibility — How easy is the learner to understand without looking at the transcript?**

1 = rất khó hiểu; 3 = phần lớn hiểu được; 5 = rất rõ và hiểu dễ dàng. Không tự động trừ điểm vì accent.

**Prosody — How appropriate are the rhythm, phrasing, stress and intonation?**

Nghe nhịp câu, chia cụm ý, sentence stress và ngữ điệu. Không chấm trùng Fluency.
""")

    pair_ids = [item["pair_id"] for item in items]
    first_pending = next((index for index, item in enumerate(items) if not item.get("human_confirmed")), 0)
    if "teacher_rating_index" not in st.session_state:
        st.session_state["teacher_rating_index"] = first_pending
    selected_id = st.selectbox("Video", pair_ids,
                               index=min(st.session_state["teacher_rating_index"], len(items) - 1),
                               key="teacher_rating_pair")
    index = pair_ids.index(selected_id)
    item = items[index]
    raw_path = evidence / "pairs" / selected_id / "raw_evidence.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    st.video(raw["raw_duet_path"])
    st.audio(str(evidence / raw["model_input_ref"]))

    if item["quality_gate"] == "AMBER":
        existing = item.get("amber_scorability")
        choices = [None, "SCORABLE", "NOT_SCORABLE"]
        scorability = st.selectbox("SCORABLE / NOT SCORABLE", choices,
                                   index=choices.index(existing) if existing in choices else 0,
                                   format_func=lambda value: "— Chọn —" if value is None else value,
                                   key=f"teacher_scorability_{selected_id}")
    else:
        scorability = "SCORABLE"

    scores: dict[str, int] = {}
    if scorability != "NOT_SCORABLE":
        for name, label in (("fluency", "Fluency 1–5"),
                            ("pronunciation", "Pronunciation 1–5"),
                            ("intelligibility", "Intelligibility 1–5"),
                            ("prosody", "Prosody 1–5")):
            options = [None, 1, 2, 3, 4, 5]
            existing_score = item.get(name)
            value = st.selectbox(label, options,
                                 index=options.index(existing_score) if existing_score in options else 0,
                                 format_func=lambda score: "— Chọn điểm —" if score is None else str(score),
                                 key=f"teacher_{name}_{selected_id}")
            if isinstance(value, int):
                scores[name] = value
    pronunciation_examples = st.text_input("Pronunciation examples / problematic words (không bắt buộc)",
                                           value=item.get("pronunciation_examples", ""),
                                           key=f"teacher_pronunciation_examples_{selected_id}")
    note = st.text_input("Ghi chú ngắn (không bắt buộc)", value=item.get("note", ""),
                         key=f"teacher_note_{selected_id}")
    scores_ready = scorability == "NOT_SCORABLE" or all(name in scores for name in ("fluency", "pronunciation", "intelligibility", "prosody"))
    save_disabled = scorability is None or not scores_ready
    if st.button("Save & Next", type="primary", disabled=save_disabled, key=f"teacher_save_{selected_id}"):
        save_rating(ratings_path, selected_id, scorability, scores, note, True,
                    pronunciation_examples=pronunciation_examples)
        refreshed = json.loads(ratings_path.read_text(encoding="utf-8"))["items"]
        next_pending = next((i for i, row in enumerate(refreshed) if not row.get("human_confirmed")),
                            min(index + 1, len(items) - 1))
        st.session_state["teacher_rating_index"] = next_pending
        st.session_state.pop("teacher_rating_pair", None)
        st.rerun()
    if len(completed) == len(items):
        st.success("Đã lưu đủ 12/12. Dữ liệu vẫn còn sau khi tắt/mở lại app.")


def _phase2_assessment_result_dashboard() -> None:
    """Evidence-first result page that never displays an uncalibrated numeric score."""
    from speaking_evidence.p22 import DISCLAIMER, RATING_IDS

    evidence_root = ROOT / "assessment_runs" / "T001_p22_calibrated_v01"
    rating_root = ROOT / "human_ground_truth" / "p22a_v1"
    ratings_path = rating_root / "ratings_v2.json" if (rating_root / "ratings_v2.json").is_file() else rating_root / "ratings_v1.json"
    st.title("Phase 2 Assessment Result")
    st.warning(" · ".join(DISCLAIMER))
    pair_id = st.selectbox("Learner", list(RATING_IDS), key="p22_result_pair")
    evidence_path = evidence_root / "pairs" / pair_id / "evidence.json"
    if not evidence_path.is_file():
        st.error("Chưa có machine evidence cho video này.")
        return
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    turn = evidence["turns"][0]
    st.subheader("Transcript")
    st.write(turn["transcript"]["verbatim_transcript"])
    st.subheader("Fluency evidence")
    st.json(evidence["aggregate_fluency_evidence"])
    st.subheader("Intelligibility evidence")
    probabilities = [word.get("probability") for word in turn["transcript"].get("words", [])
                     if word.get("probability") is not None]
    st.json({"mean_word_probability": sum(probabilities) / len(probabilities) if probabilities else None,
             "word_count_with_probability": len(probabilities),
             "note": "Recognition evidence only; an ASR mismatch is not a pronunciation error."})
    st.subheader("Pronunciation")
    pronunciation_path = evidence_root / "pairs" / pair_id / "pronunciation_asr_baseline_v1.json"
    if pronunciation_path.is_file():
        pronunciation = json.loads(pronunciation_path.read_text(encoding="utf-8"))
        st.info("PRONUNCIATION EVIDENCE ONLY · WAITING FOR HUMAN CALIBRATION")
        st.json({"status": pronunciation["status"],
                 "backend_role": pronunciation["backend"]["role"],
                 "valid_analyzed_word_count": pronunciation["utterance"]["valid_analyzed_word_count"],
                 "analyzed_coverage": pronunciation["utterance"]["analyzed_coverage"],
                 "final_consonant_evidence": pronunciation["diagnostics"]["final_consonant_evidence"],
                 "human_calibrated_score": None,
                 "limitations": pronunciation["limitations"]})
    else:
        st.error("WAITING FOR HUMAN CALIBRATION")
    st.subheader("ASR-assisted Reading Completeness")
    completeness_path = evidence_root / "pairs" / pair_id / "reading_completeness_v1.json"
    if completeness_path.is_file():
        completeness = json.loads(completeness_path.read_text(encoding="utf-8"))
        st.json({key: completeness.get(key) for key in
                 ("coverage", "matched_sequence", "omissions", "insertions", "transcript_source", "warning")})
    else:
        st.info("WAITING FOR TARGET CONFIRMATION OR COMPLETENESS PREPARATION")
    st.subheader("Prosody evidence")
    st.json(turn["acoustic"])

    summary_path = evidence_root / "calibration_summary.json"
    if not summary_path.is_file():
        completed = 0
        if ratings_path.is_file():
            ratings = json.loads(ratings_path.read_text(encoding="utf-8"))["items"]
            completed = sum(item.get("human_confirmed") is True for item in ratings)
        st.error("WAITING FOR HUMAN CALIBRATION")
        st.caption(f"Human ratings: {completed}/12. Không có numeric score giả.")
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    score = next((item for item in summary.get("scores", []) if item["pair_id"] == pair_id), None)
    if not score:
        st.error("WAITING FOR HUMAN CALIBRATION")
    else:
        st.subheader("Score / status")
        st.json(score)


current_config = _sidebar_config()
if st.query_params.get("mode") == "p21b" and "lab_workspace_mode" not in st.session_state:
    st.session_state["lab_workspace_mode"] = "P2.1b Validation"
if st.query_params.get("mode") == "p22a" and "lab_workspace_mode" not in st.session_state:
    st.session_state["lab_workspace_mode"] = "P2.2A Calibration"
if st.query_params.get("mode") == "teacher" and "lab_workspace_mode" not in st.session_state:
    st.session_state["lab_workspace_mode"] = "Teacher Rating — P2.2A"
if st.query_params.get("mode") == "p22result" and "lab_workspace_mode" not in st.session_state:
    st.session_state["lab_workspace_mode"] = "Phase 2 Assessment Result"
workspace_mode = st.sidebar.radio("Workspace mode", ["Individual Research Console", "Cohort P1.4", "Phase 2 Evidence", "P2.1b Validation", "P2.2A Calibration", "Teacher Rating — P2.2A", "Phase 2 Assessment Result"],
                                  key="lab_workspace_mode")
if workspace_mode == "Cohort P1.4":
    _cohort_dashboard(current_config)
    st.stop()
if workspace_mode == "Phase 2 Evidence":
    _phase2_evidence_dashboard()
    st.stop()
if workspace_mode == "P2.1b Validation":
    _p21b_validation_dashboard()
    st.stop()
if workspace_mode == "P2.2A Calibration":
    _p22a_dashboard()
    st.stop()
if workspace_mode == "Teacher Rating — P2.2A":
    _teacher_rating_dashboard()
    st.stop()
if workspace_mode == "Phase 2 Assessment Result":
    _phase2_assessment_result_dashboard()
    st.stop()
_run_history()
_input_panel(current_config)

active = st.session_state.get("lab_active_run")
if active:
    run_dir = Path(active)
    try:
        result = load_result(run_dir)
        run_config = json.loads((run_dir/"config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        st.error(f"Could not load saved run: {exc}")
    else:
        _summary(result, run_dir)
        st.subheader("3 · Interactive timeline")
        if "original_vad_segments" not in result:
            st.info("This older run has no serialized Original VAD intervals; rerun the pair to show that timeline row.")
        show_residual = st.checkbox("Show residual VAD row", key=f"lab_show_residual_{run_dir.name}")
        st.plotly_chart(timeline_figure(result, show_residual), width="stretch", theme=None,
                        key=f"lab_timeline_{run_dir.name}")
        _load_review_state(run_dir, result)
        st.subheader("4 · Segment review")
        if result.get("learner_segments"):
            if st.session_state.pop("lab_force_table_review", False):
                st.session_state["lab_review_mode"] = "Table review"
            mode = st.radio("Review mode", ["Table review", "Quick review · predicted learner only"],
                            horizontal=True, key="lab_review_mode")
            if mode == "Table review":
                _review_table(run_dir, result)
            else:
                _quick_review(run_dir, result)
        else:
            st.info("No confident learner segments were emitted. Inspect alignment/cancellation warnings below.")
        with st.expander("Completed Duet video", expanded=False):
            video = next((run_dir/"inputs").glob("duet.*"), None)
            if video and video.is_file():
                st.video(str(video))
        _validation(run_dir, result, run_config)
        _optimization(run_dir, result, run_config)
        _diagnostics(run_dir, result, run_config)
else:
    st.info("Choose the original and completed Duet above, then click Run Analysis.")
