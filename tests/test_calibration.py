from __future__ import annotations

import numpy as np
import pytest

from duet_segmenter.cancellation import compare_backends
from duet_segmenter.leakage import diagnose
from duet_segmenter.optimization import optimize_vad
from duet_segmenter.pipeline import load_config
from duet_segmenter.vad import SileroDetector


def test_cached_silero_timestamps_match_baseline_inference():
    torch = pytest.importorskip("torch")
    silero = pytest.importorskip("silero_vad")
    audio = np.zeros(16_000*3, dtype=np.float32)
    audio[16_000:32_000] = 0.05*np.random.default_rng(20).standard_normal(16_000)
    cfg = load_config()["vad"]
    detector = SileroDetector()
    cached = detector.infer(audio, 16_000)
    actual = cached.timestamps(cfg).segments
    direct = silero.get_speech_timestamps(torch.from_numpy(audio), detector.model,
        threshold=cfg["threshold"], sampling_rate=16_000,
        min_speech_duration_ms=cfg["min_speech_duration_ms"],
        min_silence_duration_ms=cfg["min_silence_duration_ms"],
        speech_pad_ms=cfg["speech_pad_ms"])
    assert actual == [{"start": s["start"]/16_000, "end": s["end"]/16_000} for s in direct]
    assert cached.timestamps(dict(cfg, threshold=.65)).segments is not None


def test_multi_feature_leakage_filter_keeps_unrelated_overlap():
    sr = 16_000
    rng = np.random.default_rng(10)
    reference = rng.standard_normal(sr).astype(np.float32)*.1
    residual = np.concatenate([reference[:sr//2]*.8,
        rng.standard_normal(sr//2).astype(np.float32)*.1])
    near = .3*reference + residual
    segments = [{"start": 0., "end": .5, "confidence": .9, "overlap_candidate": True},
                {"start": .5, "end": 1., "confidence": .9, "overlap_candidate": True}]
    accepted, rejected, details = diagnose(segments, [{"start": 0., "end": 1.}],
        near, reference, residual, sr, .3, load_config()["leakage"])
    assert len(rejected) == 1 and len(accepted) == 1
    assert details[0]["timeline_state"] == "REFERENCE_LEAKAGE_CANDIDATE"
    assert details[1]["timeline_state"] == "TRUE_OVERLAP_CANDIDATE"


def test_optimizer_requires_human_ground_truth(tmp_path):
    with pytest.raises(FileNotFoundError):
        optimize_vad(tmp_path, {"timeline": {"duet_duration_sec": 1.}}, load_config())


def test_auto_backend_comparison_is_deterministic_on_known_mixture():
    rng = np.random.default_rng(8)
    far = rng.standard_normal(16_000*2).astype(np.float32)*.1
    near = .35*far
    selected, comparison = compare_backends(near, far, 16_000, load_config()["cancellation"])
    assert comparison["selected_backend"] == selected.backend
    assert {row["backend"] for row in comparison["candidates"]} >= {"linear"}
    assert selected.reference_suppression_db >= 5
