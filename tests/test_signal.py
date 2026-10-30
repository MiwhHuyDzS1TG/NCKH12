from __future__ import annotations

import copy

import numpy as np
from scipy import signal

from duet_segmenter.alignment import align, build_aligned_reference
from duet_segmenter.cancellation import LinearCanceller
from duet_segmenter.pipeline import load_config

SR = 16_000


def speechlike(seconds: float, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    length = round(seconds*SR)
    noise = signal.sosfilt(signal.butter(3, [180, 3500], btype="bandpass", fs=SR, output="sos"),
                          rng.standard_normal(length))
    envelope = np.zeros(length)
    for start in np.arange(0.3, seconds-0.3, 0.7):
        lo = round(start*SR)
        hi = min(length, lo+round(0.38*SR))
        envelope[lo:hi] = np.hanning(2*(hi-lo))[hi-lo:]
    return (0.12*noise*envelope).astype(np.float32)


def mixture(original: np.ndarray, duet_seconds: float, b: float, gain: float, a: float = 1., learner: np.ndarray | None = None) -> np.ndarray:
    aligned = build_aligned_reference(original, round(duet_seconds*SR), SR, a, b)
    return (gain*aligned+(learner if learner is not None else 0)).astype(np.float32)


def alignment_cfg() -> dict:
    cfg = copy.deepcopy(load_config()["alignment"])
    cfg.update(anchor_count=5, anchor_duration_sec=0.45, coarse_max_offset_sec=2.0,
               min_coarse_peak_to_background=1.1, min_anchor_correlation=0.45)
    return cfg


def test_synthetic_known_negative_offset():
    original = speechlike(9)
    duet = mixture(original, 10, -0.3125, 0.35)
    result = align(original, duet, SR, alignment_cfg())
    assert result.status == "ok"
    assert abs(result.b+0.3125) < 0.008
    assert sum(x.accepted for x in result.anchors) >= 3
    assert min(x.correlation for x in result.anchors if x.accepted) > 0.9


def test_alignment_with_learner_noise_and_linear_clock_drift():
    original = speechlike(10, seed=9)
    rng = np.random.default_rng(22)
    learner = np.zeros(round(11*SR), dtype=np.float32)
    learner[round(3.2*SR):round(4.7*SR)] = 0.025*rng.standard_normal(round(1.5*SR))
    duet = mixture(original, 11, 0.19, 0.34, a=1.0002, learner=learner)
    result = align(original, duet, SR, alignment_cfg())
    assert result.status == "ok"
    assert abs(result.b-0.19) < 0.012
    assert abs(result.a-1.0002) < 0.001


def test_gain_scaled_reference_mixture_cancels():
    original = speechlike(6, seed=17)
    reference = build_aligned_reference(original, len(original), SR, 1., 0.)
    learner = np.zeros_like(reference)
    learner[round(2*SR):round(3*SR)] = 0.025*speechlike(1, seed=20)/0.12
    near = 0.34*reference+learner
    cfg = load_config()["cancellation"]
    result = LinearCanceller().cancel(near, reference, SR, cfg)
    assert result.status == "ok"
    assert abs(result.estimated_reference_gain-0.34) < 0.02
    assert result.reference_suppression_db > 8
    assert np.sqrt(np.mean(result.residual**2)) < np.sqrt(np.mean(near**2))*0.5


def test_reference_zeros_in_intro_and_outro_with_unequal_lengths():
    original = speechlike(3)
    reference = build_aligned_reference(original, round(5*SR), SR, 1., 0.5)
    assert len(reference) == round(5*SR)
    assert np.all(reference[:round(0.5*SR)] == 0)
    assert np.all(reference[round(3.5*SR):] == 0)
    assert np.any(reference[round(1*SR):round(3*SR)] != 0)


def test_unrelated_audio_reports_alignment_unreliable():
    original = speechlike(8, seed=29)
    duet = speechlike(9, seed=30)
    result = align(original, duet, SR, alignment_cfg())
    assert result.status == "alignment_unreliable"


def test_unrelated_reference_reports_cancellation_unreliable():
    original = speechlike(5, seed=31)
    unrelated = speechlike(5, seed=32)
    result = LinearCanceller().cancel(unrelated, original, SR, load_config()["cancellation"])
    assert result.status == "cancellation_unreliable"
