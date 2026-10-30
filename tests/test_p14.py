from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np

from duet_segmenter.audibility import measure_reference_presence
from duet_segmenter.cohort import _summary, audit_outcome, cohort_manifest, run_cohort
from duet_segmenter.p14b import select_green_audit_v2
from duet_segmenter.p14c import run_p14c
from duet_segmenter.pipeline import load_config
from duet_segmenter.quality import background_interference, low_speech_level, measure_audio_quality
from duet_segmenter.scorability import (decide_scorability, deterministic_audit,
    deterministic_stratified_split, deterministic_stratified_split_v2)
from duet_segmenter.visual import _fingerprint, _normalize_duet_layout, align_fingerprints


def test_visual_side_offset_and_reencode_tolerance():
    rng = np.random.default_rng(3)
    anchors = np.arange(2., 14., 2.)
    templates = rng.standard_normal((len(anchors), 32*56*2)).astype(np.float32)
    templates /= np.linalg.norm(templates, axis=1, keepdims=True)
    duet_times = np.arange(0, 18, .25)
    left = rng.standard_normal((len(duet_times), templates.shape[1])).astype(np.float32)
    left /= np.linalg.norm(left, axis=1, keepdims=True)
    right = left.copy()
    for time, feature in zip(anchors, templates):
        right[np.argmin(abs(duet_times-(time+.5)))] = feature
    cfg = dict(load_config()["visual"], min_match_score=.9, max_anchor_mad_sec=.1)
    result = align_fingerprints(anchors, templates, duet_times, {"left": left, "right": right}, cfg)
    assert result.status == "ok" and result.template_side == "right"
    assert abs(result.b-.5) < .01 and abs(result.a-1) < .001
    frame = (rng.random((240, 160, 3))*255).astype(np.uint8)
    encoded = cv2.imdecode(cv2.imencode(".jpg", cv2.resize(frame, (120, 180)),
                                       [cv2.IMWRITE_JPEG_QUALITY, 55])[1], cv2.IMREAD_COLOR)
    assert float(_fingerprint(frame) @ _fingerprint(encoded)) > .9


def test_visual_consensus_rejects_repeated_edge_frame_outliers():
    rng = np.random.default_rng(31)
    anchors = np.arange(2., 54., 4.)
    templates = rng.standard_normal((len(anchors), 32*56*2)).astype(np.float32)
    templates /= np.linalg.norm(templates, axis=1, keepdims=True)
    duet_times = np.arange(0., 58., .25)
    right = rng.standard_normal((len(duet_times), templates.shape[1])).astype(np.float32)
    right /= np.linalg.norm(right, axis=1, keepdims=True)
    left = right.copy()
    for index, (time, feature) in enumerate(zip(anchors, templates)):
        offset = .75 if index == 0 else (-1. if index == len(anchors)-1 else -.25)
        right[np.argmin(abs(duet_times-(time+offset)))] = feature
    cfg = dict(load_config()["visual"], min_match_score=.9, max_anchor_mad_sec=.35)
    result = align_fingerprints(anchors, templates, duet_times, {"left": left, "right": right}, cfg)
    assert result.status == "ok"
    assert result.accepted_anchor_count == len(anchors)-2
    assert result.accepted_anchor_coverage >= .70
    assert abs(result.a-1.) < .002 and abs(result.b+.25) < .02


def test_visual_layout_normalization_removes_plain_letterbox():
    rng = np.random.default_rng(19)
    content = (rng.random((56, 64))*220+20).astype(np.uint8)
    letterboxed = np.zeros((112, 128), dtype=np.uint8)
    letterboxed[28:84, 32:96] = content
    normalized = _normalize_duet_layout(letterboxed)
    assert normalized.shape == (56, 64)
    assert float(_fingerprint(normalized[:, 32:]) @ _fingerprint(content[:, 32:])) > .999


def test_muted_and_present_reference_detection():
    cfg = load_config()["audio_presence"]
    sr = 16_000
    rng = np.random.default_rng(4)
    reference = (.05*rng.standard_normal(sr*5)).astype(np.float32)
    independent = (.05*rng.standard_normal(sr*5)).astype(np.float32)
    vad = [{"start": 0., "end": 5.}]
    muted = measure_reference_presence(independent, reference, sr, vad, cfg)
    present = measure_reference_presence(.5*reference+.05*independent, reference, sr, vad, cfg)
    assert muted.audio_state == "CLEAN_MUTED"
    assert present.audio_state == "REFERENCE_PRESENT"
    assert present.score > muted.score
    assert "raw_waveform_correlation_p95" in present.features
    assert "reference_like_window_fraction" in present.features
    assert present.features["longest_reference_like_run_windows"] > 0


def test_intermittent_reference_is_not_false_clean_and_clean_stays_clean():
    cfg = load_config()["audio_presence"]
    sr = 16_000
    rng = np.random.default_rng(41)
    reference = (.05*rng.standard_normal(sr*10)).astype(np.float32)
    independent = (.05*rng.standard_normal(sr*10)).astype(np.float32)
    intermittent = independent.copy()
    intermittent[3*sr:5*sr] += reference[3*sr:5*sr]
    vad = [{"start": 0., "end": 10.}]
    clean = measure_reference_presence(independent, reference, sr, vad, cfg)
    detected = measure_reference_presence(intermittent, reference, sr, vad, cfg)
    assert clean.audio_state == "CLEAN_MUTED"
    assert detected.audio_state != "CLEAN_MUTED"
    assert detected.features["localized_evidence_window_count"] >= 1


def test_smart_path_and_uncancelable_quality_states():
    cfg = load_config()["scorability"]
    clean = decide_scorability(True, "CLEAN_MUTED", None, 2., 5., 0, 0, cfg)
    bad = decide_scorability(True, "REFERENCE_PRESENT",
        {"status": "cancellation_unreliable", "reference_suppression_db": 2.,
         "residual_reference_similarity": .7}, 2., 5., 0, 0, cfg)
    good = decide_scorability(True, "REFERENCE_PRESENT",
        {"status": "ok", "reference_suppression_db": 12.,
         "residual_reference_similarity": .1}, 2., 5., 0, 0, cfg)
    assert clean["scorability_status"] == "SCORABLE_CLEAN"
    assert bad["scorability_status"] == "UNSCORABLE_REFERENCE_OVERLAP" and bad["quality_gate"] == "RED"
    assert good["scorability_status"] == "SCORABLE_AFTER_CANCELLATION"


def test_manifest_split_audit_and_summary_are_deterministic(tmp_path):
    for name in ("b.mp4", "a.mov", "ignore.txt"):
        (tmp_path/name).write_bytes(b"x")
    manifest = cohort_manifest("T001", tmp_path)
    assert [x["pair_id"] for x in manifest] == ["T001-D001", "T001-D002"]
    rows = [{"pair_id": f"P{i}", "audio_state": "CLEAN_MUTED" if i < 6 else "REFERENCE_PRESENT",
             "quality_gate": "GREEN" if i != 9 else "RED", "status": "ok",
             "selected_cancellation_backend": "NONE", "scorability_status": "SCORABLE_CLEAN",
             "suspicious_interval_count": i % 2} for i in range(10)]
    config = load_config()
    assert deterministic_audit([x["pair_id"] for x in rows[:9]], .1, 5, 99) == deterministic_audit(
        [x["pair_id"] for x in rows[:9]], .1, 5, 99)
    split = deterministic_stratified_split(rows, .25, 99)
    assert set(split["development"]).isdisjoint(split["holdout"])
    reviewed = {"P1", "P8"}
    split_v2 = deterministic_stratified_split_v2(rows, reviewed, .25, 99, 3)
    assert split_v2 == deterministic_stratified_split_v2(rows, reviewed, .25, 99, 3)
    assert reviewed.isdisjoint(split_v2["holdout"])
    assert len(split_v2["holdout"]) == 3
    summary = _summary(rows, config)
    assert summary["total_duets"] == 10 and summary["green_audit"]["status"] == "PENDING HUMAN AUDIT"
    assert audit_outcome({"tolerance": .05, "items": [{"audit": "PASS"}]})["validated"] is True
    assert audit_outcome({"tolerance": .05, "items": [{"audit": "FAIL"}]})["status"] == "FAILED"


def test_green_audit_v2_uses_only_supplied_development_green_rows():
    rows = [{"pair_id": f"P{i}", "quality_gate": "GREEN",
             "reference_audio_presence_features": {"logmel_similarity_max": i/10},
             "audio_quality_features": {"background_rms_p90": i/100}}
            for i in range(10)]
    selected = select_green_audit_v2(rows[:8], {"P1"}, 6, 12)
    ids = {item["pair_id"] for item in selected}
    assert "P1" not in ids
    assert ids <= {f"P{i}" for i in range(8)}
    assert len(ids) == 6


def test_background_interference_requires_loud_tonal_background_and_poor_ratio():
    cfg = load_config()["audio_quality"]
    sr = 16_000
    t = np.arange(sr*4)/sr
    music = (.08*np.sin(2*np.pi*220*t)).astype(np.float32)
    audio = music.copy()
    audio[sr:3*sr] += (.04*np.sin(2*np.pi*700*t[:2*sr])).astype(np.float32)
    features = measure_audio_quality(audio, sr, [{"start": 1., "end": 3.}])
    assert background_interference(features, cfg)
    clean = dict(features, background_rms_p90=.001, speech_to_background_db=20.)
    assert not background_interference(clean, cfg)


def test_low_speech_level_requires_all_three_weak_recording_signals():
    cfg = load_config()["audio_quality"]
    d030 = {"learner_frame_fraction": .4, "speech_rms_median": .00839,
            "rms_p90": .01302, "speech_to_background_db": 14.54}
    assert low_speech_level(d030, cfg)
    for changed in ({"speech_rms_median": .01627}, {"rms_p90": .02920},
                    {"speech_to_background_db": 17.06}, {"learner_frame_fraction": 0.}):
        assert not low_speech_level(d030 | changed, cfg)
    scored = decide_scorability(True, "CLEAN_MUTED", None, 2., 5., 0, 0,
                                load_config()["scorability"], has_low_speech_level=True)
    assert (scored["quality_gate"], scored["scorability_status"],
            scored["quality_gate_reasons"]) == ("AMBER", "REVIEW_REQUIRED", ["LOW_SPEECH_LEVEL"])
    both = decide_scorability(True, "CLEAN_MUTED", None, 2., 5., 0, 0,
                              load_config()["scorability"], has_background_interference=True,
                              has_low_speech_level=True)
    assert both["quality_gate_reasons"] == ["BACKGROUND_INTERFERENCE", "LOW_SPEECH_LEVEL"]


def test_batch_continues_after_pair_failure(tmp_path, monkeypatch):
    duet_dir = tmp_path/"duets"
    duet_dir.mkdir()
    for name in ("a.mp4", "b.mp4"):
        (duet_dir/name).write_bytes(name.encode())
    profile = SimpleNamespace(profile={"template_sha256": "abc"})
    monkeypatch.setattr("duet_segmenter.cohort.build_template_profile", lambda *a, **k: profile)
    calls = {"count": 0}
    def fake_run(profile, source, output, config, pair_id):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("synthetic failure")
        return {"status": "ok", "visual_alignment": {"visual_match_score": .99, "template_side": "right"},
            "audio_state": "CLEAN_MUTED", "reference_audio_presence_score": .05,
            "selected_audio_path": "RAW_DUET", "selected_cancellation_backend": "NONE",
            "cancellation_diagnostics": None, "scorability_status": "SCORABLE_CLEAN",
            "scorability_reasons": [], "quality_gate": "GREEN", "quality_gate_reasons": [],
            "learner_duration_sec": 2., "learner_segments": [{"start": 0., "end": 2.}],
            "reference_leakage_candidates": [], "overlap_candidates": [], "suspicious_intervals": [],
            "warnings": [], "runtime_sec": .1}
    monkeypatch.setattr("duet_segmenter.cohort.run_profiled", fake_run)
    output = tmp_path/"out"
    output.mkdir()
    historical = {"seed": 1, "items": [{"pair_id": "T001-D001", "audit": "FAIL",
                                           "reason": "historical"}], "status": "FAILED"}
    historical_text = __import__("json").dumps(historical, indent=2)
    (output/"green_audit.json").write_text(historical_text, encoding="utf-8")
    result = run_cohort(tmp_path/"template.mp4", duet_dir, output, "T001", load_config())
    assert len(result["rows"]) == 2
    assert result["rows"][0]["status"] == "ok"
    assert result["rows"][1]["status"] == "error"
    assert (output/"green_audit.json").read_text(encoding="utf-8") == historical_text
    assert (output/"green_audit_v2.json").is_file()
    split_v2 = __import__("json").loads((output/"data_split_v2.json").read_text(encoding="utf-8"))
    assert "T001-D001" in split_v2["development"]
    assert "T001-D001" not in split_v2["holdout"]
