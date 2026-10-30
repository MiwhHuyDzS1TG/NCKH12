"""Two-stage log-Mel / raw-PCM reference alignment."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import signal


@dataclass
class Anchor:
    original_time: float
    best_offset: float
    correlation: float
    accepted: bool = False

    def as_dict(self) -> dict:
        return vars(self)


@dataclass
class AlignmentResult:
    status: str
    coarse_offset_sec: float
    peak_score: float
    peak_to_background_score: float
    a: float
    b: float
    offset_median: float
    offset_std: float
    offset_range: float
    offset_mad: float
    detrended_offset_range: float
    anchors: list[Anchor]
    warnings: list[str] = field(default_factory=list)
    curve_offsets_sec: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)
    curve_scores: np.ndarray = field(default_factory=lambda: np.array([]), repr=False)

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if k not in ("curve_offsets_sec", "curve_scores", "anchors")} | {"anchors": [x.as_dict() for x in self.anchors]}


def _hz_to_mel(hz: np.ndarray) -> np.ndarray:
    return 2595 * np.log10(1 + hz / 700)


def _mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700 * (10 ** (mel / 2595) - 1)


def logmel(audio: np.ndarray, sample_rate: int, hop_sec: float, bands: int = 32) -> np.ndarray:
    """Small scipy-only log-Mel implementation; rows are time frames."""
    hop = max(1, round(hop_sec * sample_rate))
    nfft = 1024
    _, _, z = signal.stft(audio, sample_rate, nperseg=nfft, noverlap=nfft-hop,
                          nfft=nfft, boundary="zeros", padded=False)
    power = np.abs(z).astype(np.float32) ** 2
    freqs = np.linspace(0, sample_rate / 2, nfft // 2 + 1)
    edges = _mel_to_hz(np.linspace(_hz_to_mel(np.array(100)), _hz_to_mel(np.array(7600)), bands + 2))
    filters = np.zeros((bands, len(freqs)), dtype=np.float32)
    for j in range(bands):
        lo, mid, hi = edges[j:j+3]
        filters[j] = np.maximum(0, np.minimum((freqs-lo)/(mid-lo), (hi-freqs)/(hi-mid)))
        filters[j] /= max(filters[j].sum(), 1e-8)
    features = np.log1p(1e5 * (filters @ power)).T
    return features.astype(np.float32)


def coarse_alignment(original: np.ndarray, duet: np.ndarray, sample_rate: int, cfg: dict) -> tuple[float, float, float, np.ndarray, np.ndarray]:
    hop_sec = float(cfg["coarse_hop_sec"])
    x = logmel(original, sample_rate, hop_sec)
    y = logmel(duet, sample_rate, hop_sec)
    # Normalize each band to damp gain changes and learner mixture interference.
    for f in (x, y):
        f -= np.mean(f, axis=0, keepdims=True)
        f /= np.maximum(np.std(f, axis=0, keepdims=True), 0.1)
        np.clip(f, -4, 4, out=f)
    nx, ny = len(x), len(y)
    score = np.zeros(nx + ny - 1, dtype=np.float64)
    for j in range(x.shape[1]):
        score += signal.correlate(y[:, j], x[:, j], mode="full", method="fft")
    lags = signal.correlation_lags(ny, nx, mode="full")
    # Exact overlap-normalized denominator at each lag.
    x_energy = np.r_[0., np.cumsum(np.sum(x.astype(np.float64)**2, axis=1))]
    y_energy = np.r_[0., np.cumsum(np.sum(y.astype(np.float64)**2, axis=1))]
    xs = np.maximum(0, -lags)
    ys = np.maximum(0, lags)
    overlap = np.minimum(nx-xs, ny-ys)
    valid = (overlap >= cfg["coarse_min_overlap_fraction"] * nx) & (np.abs(lags*hop_sec) <= cfg["coarse_max_offset_sec"])
    denom = np.sqrt(np.maximum((x_energy[xs+overlap]-x_energy[xs]) * (y_energy[ys+overlap]-y_energy[ys]), 1e-12))
    score /= denom
    score[~valid] = np.nan
    if not np.any(valid):
        raise ValueError("No sufficient audio overlap within coarse alignment search range")
    best = int(np.nanargmax(score))
    peak = float(score[best])
    background = float(np.nanmedian(np.abs(score[valid])))
    return float(lags[best]*hop_sec), peak, peak/max(background, 1e-6), lags[valid]*hop_sec, score[valid]


def _fine_anchor(original: np.ndarray, duet: np.ndarray, sr: int, start: int, length: int, coarse_sec: float, radius_ms: float) -> Anchor | None:
    expected = round(start + coarse_sec*sr)
    radius = round(radius_ms*sr/1000)
    scan_start = expected-radius
    scan_end = expected+radius+length
    if scan_start < 0 or scan_end > len(duet):
        return None
    template = original[start:start+length].astype(np.float64)
    template -= template.mean()
    candidates = duet[scan_start:scan_end].astype(np.float64)
    candidates -= np.mean(candidates)
    numerator = signal.correlate(candidates, template, mode="valid", method="fft")
    # Remove local DC via exact rolling sums.
    sum_y = np.r_[0., np.cumsum(candidates)]
    sum_y2 = np.r_[0., np.cumsum(candidates**2)]
    rolling_energy = sum_y2[length:]-sum_y2[:-length] - (sum_y[length:]-sum_y[:-length])**2/length
    normalized = numerator / np.sqrt(np.maximum(np.sum(template**2)*rolling_energy, 1e-12))
    i = int(np.argmax(normalized))
    return Anchor((start+length/2)/sr, (scan_start+i-start)/sr, float(normalized[i]))


def fine_alignment(original: np.ndarray, duet: np.ndarray, sr: int, coarse_sec: float, cfg: dict) -> list[Anchor]:
    length = round(cfg["anchor_duration_sec"]*sr)
    bins = int(cfg["anchor_count"])
    if len(original) < 2*length:
        raise ValueError("Original audio is too short for fine alignment anchors")
    anchors = []
    # Pick one energetic and variable window per equally spaced bin.
    bin_edges = np.linspace(length, len(original)-length, bins+1, dtype=int)
    stride = max(sr//4, 1)
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        starts = np.arange(lo, max(lo+1, hi-length//2), stride)
        if not len(starts):
            starts = np.array([lo])
        scores = []
        for s in starts:
            w = original[s:s+length]
            scores.append(float(np.mean(w*w) * (1 + np.mean(np.abs(np.diff(w))) * 30)))
        for s in starts[np.argsort(scores)[-3:][::-1]]:
            anchor = _fine_anchor(original, duet, sr, int(s), length, coarse_sec, cfg["fine_search_ms"])
            if anchor is not None:
                anchors.append(anchor)
                break
    return anchors


def align(original: np.ndarray, duet: np.ndarray, sample_rate: int, cfg: dict) -> AlignmentResult:
    coarse, peak, ratio, offsets, curve = coarse_alignment(original, duet, sample_rate, cfg)
    anchors = fine_alignment(original, duet, sample_rate, coarse, cfg)
    good = [p for p in anchors if p.correlation >= cfg["min_anchor_correlation"]]
    raw_offsets = np.array([p.best_offset for p in good], dtype=float)
    warnings = []
    if len(good):
        median = float(np.median(raw_offsets))
        mad = float(np.median(np.abs(raw_offsets-median)))
        # Permit small linear clock drift, while rejecting distinct false peaks.
        if len(good) >= 3:
            times = np.array([p.original_time for p in good])
            slope, intercept = np.polyfit(times, raw_offsets, 1)
            inliers = np.abs(raw_offsets-(slope*times+intercept)) <= max(cfg["max_offset_mad_ms"]/1000, 3*mad)
            if np.count_nonzero(inliers) >= 3:
                slope, intercept = np.polyfit(times[inliers], raw_offsets[inliers], 1)
                for p, accepted in zip(good, inliers):
                    p.accepted = bool(accepted)
            else:
                slope, intercept = 0., median
        else:
            slope, intercept = 0., median
        accepted = [p for p in good if p.accepted]
        if not accepted:
            accepted = good
            for p in accepted:
                p.accepted = True
        accepted_offsets = np.array([p.best_offset for p in accepted])
        std = float(np.std(accepted_offsets))
        span = float(np.ptp(accepted_offsets))
        detrended = accepted_offsets-(slope*np.array([p.original_time for p in accepted])+intercept)
        residual_mad = float(np.median(np.abs(detrended)))
        detrended_span = float(np.ptp(detrended))
        a, b = float(1+slope), float(intercept)
        median = float(np.median(accepted_offsets))
    else:
        a, b, median, std, span, residual_mad, detrended_span = 1., coarse, coarse, float("inf"), float("inf"), float("inf"), float("inf")
    reliable = (len(accepted if len(good) else []) >= cfg["min_reliable_anchors"]
                and peak > 0 and ratio >= cfg["min_coarse_peak_to_background"]
                and residual_mad*1000 <= cfg["max_offset_mad_ms"]
                and detrended_span*1000 <= cfg["max_offset_range_ms"]
                and abs(a-1) <= cfg["max_time_scale_deviation"])
    if not reliable:
        warnings.append("Local waveform alignment is inconsistent or lacks strong anchors; learner segments suppressed")
    return AlignmentResult("ok" if reliable else "alignment_unreliable", coarse, peak, ratio,
                           a, b, median, std, span, residual_mad, detrended_span, anchors, warnings, offsets, curve)


def build_aligned_reference(original: np.ndarray, duet_length: int, sr: int, a: float, b: float) -> np.ndarray:
    if duet_length <= 0 or sr <= 0 or a <= 0:
        raise ValueError("Invalid timeline mapping or audio length")
    duet_indices = np.arange(duet_length, dtype=np.float64)
    original_indices = (duet_indices/sr-b)/a*sr
    return np.interp(original_indices, np.arange(len(original)), original,
                     left=0., right=0.).astype(np.float32)
