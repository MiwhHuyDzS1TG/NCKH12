"""Inspectable audio-only reference leakage diagnostics for candidate intervals."""
from __future__ import annotations

import numpy as np
from scipy.signal import stft


def _corr(x: np.ndarray, y: np.ndarray) -> float:
    x, y = x.astype(np.float64), y.astype(np.float64)
    x, y = x-x.mean(), y-y.mean()
    return float(np.dot(x, y)/np.sqrt(max(np.dot(x, x)*np.dot(y, y), 1e-18)))


def _spectral_similarity(x: np.ndarray, y: np.ndarray, sr: int) -> float:
    if len(x) < 256:
        return 0.
    _, _, xx = stft(x, sr, nperseg=512, noverlap=256)
    _, _, yy = stft(y, sr, nperseg=512, noverlap=256)
    frequencies = np.linspace(0, sr/2, xx.shape[0])
    mel = lambda hz: 2595*np.log10(1+hz/700)
    hz = lambda value: 700*(10**(value/2595)-1)
    centers = hz(np.linspace(mel(80), mel(min(7600, sr/2)), 42))
    filters = np.zeros((40, len(frequencies)))
    for index in range(40):
        left, center, right = centers[index:index+3]
        filters[index] = np.maximum(0, np.minimum(
            (frequencies-left)/max(center-left, 1e-9),
            (right-frequencies)/max(right-center, 1e-9)))
    a = np.log1p(100*(filters @ np.abs(xx)))
    b = np.log1p(100*(filters @ np.abs(yy)))
    return _corr(a.ravel(), b.ravel())


def diagnose(segments: list[dict], original_vad: list[dict], near: np.ndarray,
             reference: np.ndarray, residual: np.ndarray, sr: int, gain: float,
             cfg: dict, full_diagnostics: bool = True) -> tuple[list[dict], list[dict], list[dict]]:
    """Keep ambiguous overlap visible; filter only strong multi-feature leakage evidence."""
    accepted, rejected, diagnostics = [], [], []
    for index, item in enumerate(segments, 1):
        lo, hi = max(0, round(item["start"]*sr)), min(len(residual), round(item["end"]*sr))
        duration = (hi-lo)/sr
        overlap = sum(max(0., min(item["end"], ref["end"])-max(item["start"], ref["start"]))
                      for ref in original_vad)
        ref, res, mixture = reference[lo:hi], residual[lo:hi], near[lo:hi]
        corr = abs(_corr(res, ref)) if len(res) > 10 else 0.
        spectral = _spectral_similarity(res, ref, sr) if full_diagnostics or corr >= cfg["min_waveform_correlation"] else None
        suppression = 10*np.log10(max(float(np.sum((gain*ref)**2)), 1e-12)/
                                      max(float(np.sum(res**2)), 1e-12))
        reference_activity = overlap/max(duration, 1e-9)
        # Do not call a candidate leakage on template VAD alone: true overlap is common.
        leakage = (corr >= cfg["min_waveform_correlation"] and
                   spectral is not None and spectral >= cfg["min_spectral_similarity"] and
                   suppression <= cfg["max_local_suppression_db"] and
                   reference_activity >= cfg["min_template_overlap_ratio"])
        state = ("REFERENCE_LEAKAGE_CANDIDATE" if leakage else
                 "TRUE_OVERLAP_CANDIDATE" if item.get("overlap_candidate") else
                 "LEARNER_CANDIDATE")
        details = {"segment_id": f"S{index:03d}", "start": item["start"], "end": item["end"],
                   "duration_sec": duration, "template_overlap_ratio": min(1., overlap/max(duration, 1e-9)),
                   "residual_reference_waveform_correlation": corr,
                   "residual_reference_spectral_similarity": spectral,
                   "local_reference_suppression_db": float(suppression),
                   "reference_vad_activity": min(1., reference_activity),
                   "mean_silero_probability": item.get("confidence"),
                   "timeline_state": state, "auto_filtered": bool(leakage and cfg["enabled"])}
        diagnostics.append(details)
        enriched = dict(item) | {"segment_id": details["segment_id"],
                                 "timeline_state": state, "leakage_diagnostics": details}
        (rejected if details["auto_filtered"] else accepted).append(enriched)
    return accepted, rejected, diagnostics
