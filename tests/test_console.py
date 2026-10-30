from __future__ import annotations

import csv
import io
import json

import numpy as np
import pandas as pd
import soundfile as sf

from duet_segmenter.pipeline import load_config
from duet_speech_lab.console import (
    audio_clip_bytes, config_hash, empty_manual_dataframe, evaluate_run,
    ground_truth_rows, labeled_coverage, load_review, review_dataframe,
    safe_name, save_review, summary_metrics, timeline_figure,
)


def sample_result() -> dict:
    return {
        "status": "ok", "input_metadata": {"original": {"duration_sec": 4.}, "duet": {"duration_sec": 5.}},
        "alignment_diagnostics": {"b": -0.2, "anchors": [{"correlation": 0.9, "accepted": True}]},
        "cancellation_diagnostics": {"estimated_reference_gain": 0.34, "reference_suppression_db": 12., "backend": "linear"},
        "runtime_sec": 2.5,
        "learner_segments": [{"start": 1., "end": 2., "confidence": 0.91, "overlap_candidate": False},
                             {"start": 3., "end": 3.5, "confidence": 0.81, "overlap_candidate": True}],
        "overlap_candidates": [{"start": 3.1, "end": 3.3}],
        "outside_template_detections": [],
        "original_vad_segments": [{"start": 0.2, "end": 0.7}],
        "residual_vad_segments": [{"start": 1., "end": 2.}],
        "timeline": {"template_start_sec": 0., "template_end_sec": 4.5, "duet_duration_sec": 5.},
    }


def test_safe_run_name_hash_and_metric_summary():
    assert safe_name("main video.mp4") == "main_video"
    assert safe_name("../../a file.mp4") == "a_file"
    assert config_hash(load_config()) == config_hash(load_config())
    summary = summary_metrics(sample_result())
    assert summary["learner_count"] == 2
    assert summary["learner_duration"] == 1.5
    assert summary["anchor_median"] == 0.9


def test_review_export_keeps_prediction_separate_and_allows_missed_speech(tmp_path):
    result = sample_result()
    (tmp_path/"result.json").write_text(json.dumps(result), encoding="utf-8")
    original_json = (tmp_path/"result.json").read_bytes()
    review = review_dataframe(result)
    review.loc[0, ["start", "end", "review_label"]] = [1.1, 2.1, "LEARNER"]
    review.loc[1, "review_label"] = "ORIGINAL"
    manual = pd.DataFrame([{"start": 2.3, "end": 2.8, "label": "LEARNER", "notes": "missed turn"}],
                          columns=["start", "end", "label", "notes"])
    gt_path, rows = save_review(tmp_path, review, manual, result)
    assert gt_path is not None and gt_path.is_file()
    assert (tmp_path/"review.json").is_file()
    assert (tmp_path/"result.json").read_bytes() == original_json
    with gt_path.open(newline="", encoding="utf-8") as handle:
        exported = list(csv.DictReader(handle))
    assert len(exported) == 3
    assert {row["label"] for row in exported} == {"LEARNER", "ORIGINAL"}
    assert rows[0]["start"] == 1.1
    restored_review, restored_manual = load_review(tmp_path, result)
    assert restored_review.loc[0, "review_label"] == "LEARNER"
    assert restored_manual.loc[0, "label"] == "LEARNER"
    metrics = evaluate_run(tmp_path, result, load_config())
    assert metrics["learner_precision"] is not None
    assert metrics["learner_recall"] is not None
    assert metrics["learner_f1"] is not None
    assert metrics["validation_scope"] == "reviewed_intervals_only"
    assert (tmp_path/"evaluation.json").is_file()


def test_invalid_corrections_and_overlaps_are_rejected():
    result = sample_result()
    review = review_dataframe(result)
    review.loc[0, "start"] = -1.
    try:
        ground_truth_rows(review, empty_manual_dataframe(), result)
    except ValueError as exc:
        assert "Invalid corrected interval" in str(exc)
    else:
        raise AssertionError("negative start must be rejected")
    review = review_dataframe(result)
    review.loc[0, "review_label"] = "LEARNER"
    manual = pd.DataFrame([{"start": 1.5, "end": 2.5, "label": "SILENCE", "notes": ""}])
    try:
        ground_truth_rows(review, manual, result)
    except ValueError as exc:
        assert "overlap" in str(exc).lower()
    else:
        raise AssertionError("conflicting annotations must be rejected")


def test_audio_review_uses_native_stereo_source_and_context(tmp_path):
    sr = 44_100
    raw = np.tile(np.array([[0.1, -0.2]], dtype=np.float32), (sr*3, 1))
    source = tmp_path/"duet_source_audio.wav"
    sf.write(source, raw, sr, subtype="PCM_16")
    clip, lo, hi, out_sr, channels = audio_clip_bytes(source, 1., 2., 0.5)
    assert (lo, hi, out_sr, channels) == (0.5, 2.5, sr, 2)
    audio, clip_sr = sf.read(io.BytesIO(clip), dtype="float32", always_2d=True)
    assert clip_sr == sr and len(audio) == sr*2
    assert abs(float(audio[:, 0].mean())-0.1) < 0.001
    assert abs(float(audio[:, 1].mean())+0.2) < 0.001


def test_interactive_timeline_has_required_rows_and_hover_fields():
    figure = timeline_figure(sample_result(), show_residual=True)
    assert [trace.name for trace in figure.data[:5]] == ["Original", "Predicted Learner", "Overlap", "Outside Template", "Residual Vad"]
    learner_trace = figure.data[1]
    assert list(learner_trace.x) == [1., 0.5]
    assert learner_trace.customdata[0][4] == 0.91
    assert learner_trace.customdata[1][5] is True
    assert "Duration" in learner_trace.hovertemplate
    assert labeled_coverage([{"start": 0., "end": 1.}, {"start": 2., "end": 3.}], 5.) == 0.4
