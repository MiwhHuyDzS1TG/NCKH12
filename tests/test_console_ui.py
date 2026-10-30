"""Drive the Streamlit quick-review, save, and evaluation buttons in isolation."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from streamlit.testing.v1 import AppTest

from duet_segmenter.pipeline import load_config


def test_streamlit_review_save_and_evaluate(tmp_path, monkeypatch):
    run_root = tmp_path/"runs"
    run_dir = run_root/"20260101_000000_test"
    (run_dir/"inputs").mkdir(parents=True)
    (run_dir/"inputs"/"duet.mp4").write_bytes(b"mock video path for native player")
    sr = 44_100
    sf.write(run_dir/"duet_source_audio.wav", np.zeros((sr*5, 2), dtype=np.float32), sr, subtype="PCM_16")
    result = {
        "status": "ok", "input_metadata": {"original": {"duration_sec": 4.}, "duet": {"duration_sec": 5.}},
        "alignment_diagnostics": {"coarse_offset_sec": -0.2, "b": -0.2, "a": 1.,
                                  "anchors": [{"original_time": 1., "best_offset": -0.2,
                                               "correlation": 0.9, "accepted": True}]},
        "cancellation_diagnostics": {"estimated_reference_gain": 0.34, "reference_suppression_db": 12.,
                                     "backend": "linear"},
        "runtime_sec": 2.5,
        "learner_segments": [{"start": 1., "end": 2., "confidence": 0.9, "overlap_candidate": False}],
        "overlap_candidates": [], "outside_template_detections": [],
        "original_vad_segments": [], "residual_vad_segments": [],
        "timeline": {"template_start_sec": 0., "template_end_sec": 4., "duet_duration_sec": 5.},
        "warnings": [],
    }
    (run_dir/"result.json").write_text(json.dumps(result), encoding="utf-8")
    (run_dir/"config.json").write_text(json.dumps(load_config()), encoding="utf-8")
    (run_dir/"manifest.json").write_text(json.dumps({"config_sha256_short": "testhash"}), encoding="utf-8")
    untouched_result = (run_dir/"result.json").read_bytes()
    monkeypatch.setenv("DUET_SPEECH_LAB_RUNS", str(run_root))
    app = AppTest.from_file(str(Path(__file__).parents[1]/"app.py"), default_timeout=60).run()
    assert not app.exception
    assert len(app.metric) == 15
    app.slider(key="lab_vad_threshold").set_value(0.65).run()
    assert app.slider(key="lab_vad_threshold").value == 0.65
    next(button for button in app.button if button.label == "Reset to defaults").click().run()
    assert not app.exception
    assert app.slider(key="lab_vad_threshold").value == 0.5
    app.radio(key="lab_review_mode").set_value("Quick review · predicted learner only").run()
    assert not app.exception
    app.button(key="lab_quick_accept_learner").click().run()
    assert not app.exception
    assert app.session_state["lab_review_df"].loc[0, "review_label"] == "LEARNER"
    app.button(key=f"lab_save_{run_dir.name}").click().run()
    assert not app.exception
    assert (run_dir/"review.json").is_file()
    assert (run_dir/"ground_truth.csv").is_file()
    app.button(key=f"lab_evaluate_{run_dir.name}").click().run()
    assert not app.exception
    metrics = json.loads((run_dir/"evaluation.json").read_text())
    assert metrics["learner_precision"] == 1.
    assert metrics["learner_recall"] == 1.
    assert metrics["learner_f1"] == 1.
    assert metrics["validation_scope"] == "reviewed_intervals_only"
    labels = {metric.label for metric in app.metric}
    assert "Learner precision" in labels
    assert "Learner recall" not in labels and "Learner F1" not in labels
    assert metrics["learner_recall_display"] == "NOT FULLY VERIFIED"
    assert (run_dir/"result.json").read_bytes() == untouched_result
