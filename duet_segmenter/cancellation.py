"""Known-reference cancellation, with WebRTC AEC3 and deterministic fallback."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CancellationResult:
    status: str
    residual: np.ndarray
    backend: str
    estimated_reference_gain: float
    reference_suppression_db: float
    input_reference_correlated_energy: float
    residual_energy: float
    confident_window_count: int
    analysis_window_count: int
    warnings: list[str]
    backend_comparison: dict | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if k not in {"residual", "backend_comparison"}}


def _correlation(x: np.ndarray, y: np.ndarray) -> float:
    x, y = x.astype(np.float64), y.astype(np.float64)
    x, y = x-x.mean(), y-y.mean()
    return float(np.dot(x, y)/np.sqrt(max(np.dot(x, x)*np.dot(y, y), 1e-18)))


def _quality_metrics(near: np.ndarray, far: np.ndarray, result: CancellationResult, sr: int, cfg: dict) -> dict:
    active, _, _ = select_reference_active(near, far, sr, cfg)
    width = max(1, round(cfg["analysis_window_sec"]*sr))
    correlations = []
    for start in range(0, len(far)-width+1, width):
        if np.mean(active[start:start+width]) > 0.9:
            correlations.append(abs(_correlation(far[start:start+width], result.residual[start:start+width])))
    # A quiet reference region is the closest available audio-only proxy for learner preservation.
    inactive = np.zeros(len(far), dtype=bool)
    for start in range(0, len(far), width):
        end = min(len(far), start+width)
        if np.sqrt(np.mean(far[start:end].astype(np.float64)**2)) < cfg["min_reference_rms"]:
            inactive[start:end] = True
    near_energy = float(np.mean(near[inactive]**2)) if np.any(inactive) else 0.
    residual_energy = float(np.mean(result.residual[inactive]**2)) if np.any(inactive) else 0.
    preservation = float(np.sqrt(residual_energy/max(near_energy, 1e-12))) if near_energy > 1e-8 else None
    # Reference-dominant windows are selected using the input alone, so all backends see the same mask.
    false_residual = float(np.mean(np.abs(result.residual[active]) > 0.015)) if np.any(active) else None
    return {"backend": result.backend, "status": result.status,
            "reference_suppression_db": result.reference_suppression_db,
            "residual_reference_similarity": float(np.median(correlations)) if correlations else None,
            "learner_region_preservation": preservation,
            "false_residual_speech_diagnostic": false_residual,
            "confident_window_count": result.confident_window_count}


def compare_backends(near: np.ndarray, far: np.ndarray, sr: int, cfg: dict) -> tuple[CancellationResult, dict]:
    """Compare full-length candidates on identical aligned audio; choose one whole residual."""
    candidates, unavailable = [], []
    for backend in (LinearCanceller(), WebRTCCanceller()):
        try:
            result = backend.cancel(near, far, sr, cfg)
        except (ImportError, RuntimeError) as exc:
            unavailable.append({"backend": "webrtc_aec3", "reason": str(exc)})
            continue
        candidates.append((result, _quality_metrics(near, far, result, sr, cfg)))
    if not candidates:
        raise RuntimeError("No cancellation backend is available")
    def rank(item):
        result, metrics = item
        similarity = metrics["residual_reference_similarity"]
        preservation = metrics["learner_region_preservation"]
        false_residual = metrics["false_residual_speech_diagnostic"]
        # Reliability is primary; suppression and independent residue diagnostics decide ties.
        score = (int(result.status == "ok"), round(result.reference_suppression_db, 3),
                 -round(similarity if similarity is not None else 1., 3),
                 round(min(preservation, 1.) if preservation is not None else 0., 3),
                 -round(false_residual if false_residual is not None else 1., 3),
                 int(result.backend == "linear"))
        metrics["ranking_tuple"] = list(score)
        return score
    ordered = sorted(candidates, key=rank, reverse=True)
    selected = ordered[0][0]
    comparison = {"selected_backend": selected.backend,
                  "selection_rule": "Reliable status, then measured suppression, lower reference similarity, preservation in reference-inactive regions, lower residual speech proxy; deterministic linear tie break",
                  "metrics_note": "Learner preservation and false speech are audio-only proxies, not ground-truth labels",
                  "candidates": [metrics for _, metrics in ordered], "unavailable": unavailable}
    selected.backend_comparison = comparison
    return selected, comparison


def _validate(near: np.ndarray, far: np.ndarray, sample_rate: int) -> None:
    if sample_rate != 16_000:
        raise ValueError("Cancellation requires 16 kHz mono audio")
    if near.ndim != 1 or far.ndim != 1 or len(near) != len(far) or not len(near):
        raise ValueError("near and far must be equal-length, nonempty mono arrays")
    if not np.all(np.isfinite(near)) or not np.all(np.isfinite(far)):
        raise ValueError("Cancellation input contains non-finite samples")


def select_reference_active(near: np.ndarray, far: np.ndarray, sr: int, cfg: dict) -> tuple[np.ndarray, int, int]:
    """Select high-correlation, high-reference-energy windows for gain/quality."""
    width = max(1, round(cfg["analysis_window_sec"]*sr))
    windows = []
    for start in range(0, len(far)-width+1, width):
        x = far[start:start+width].astype(np.float64)
        y = near[start:start+width].astype(np.float64)
        x -= x.mean()
        y -= y.mean()
        rms = np.sqrt(np.mean(x*x))
        if rms < cfg["min_reference_rms"]:
            continue
        corr = float(np.dot(x, y)/np.sqrt(max(np.dot(x,x)*np.dot(y,y), 1e-18)))
        if corr >= cfg["min_window_correlation"]:
            windows.append((start, corr))
    mask = np.zeros(len(far), dtype=bool)
    if windows:
        cutoff = max(cfg["min_window_correlation"], float(np.quantile([c for _, c in windows], cfg["confidence_window_quantile"])))
        for start, corr in windows:
            if corr >= cutoff:
                mask[start:start+width] = True
    return mask, len(windows), max(0, (len(far)-width+1+width-1)//width)


def _gain(near: np.ndarray, far: np.ndarray, mask: np.ndarray) -> float:
    x = far[mask].astype(np.float64)
    y = near[mask].astype(np.float64)
    denom = float(np.dot(x, x))
    if denom < 1e-12:
        return 0.
    return float(np.dot(x, y)/denom)


def _suppression(near: np.ndarray, far: np.ndarray, residual: np.ndarray, mask: np.ndarray, gain: float) -> tuple[float, float, float]:
    input_correlated = float(np.sum((gain*far[mask].astype(np.float64))**2))
    leftover = float(np.sum(residual[mask].astype(np.float64)**2))
    db = float(10*np.log10(max(input_correlated, 1e-12)/max(leftover, 1e-12)))
    return db, input_correlated, leftover


class ReferenceCanceller:
    def cancel(self, near: np.ndarray, far: np.ndarray, sample_rate: int, cfg: dict) -> CancellationResult:
        raise NotImplementedError


class LinearCanceller(ReferenceCanceller):
    def cancel(self, near: np.ndarray, far: np.ndarray, sample_rate: int, cfg: dict) -> CancellationResult:
        _validate(near, far, sample_rate)
        mask, count, total = select_reference_active(near, far, sample_rate, cfg)
        gain = _gain(near, far, mask)
        residual = (near.astype(np.float64)-gain*far.astype(np.float64)).astype(np.float32)
        db, correlated, leftover = _suppression(near, far, residual, mask, gain)
        status = "ok" if count >= cfg["min_confident_windows"] and db >= cfg["min_reference_suppression_db"] else "cancellation_unreliable"
        warnings = [] if status == "ok" else ["Reference cancellation lacks high-confidence regions or measurable suppression; learner segments suppressed"]
        return CancellationResult(status, residual, "linear", gain, db, correlated, leftover,
                                  int(np.count_nonzero(mask)//max(1,round(cfg["analysis_window_sec"]*sample_rate))), total, warnings)


class WebRTCCanceller(ReferenceCanceller):
    def cancel(self, near: np.ndarray, far: np.ndarray, sample_rate: int, cfg: dict) -> CancellationResult:
        _validate(near, far, sample_rate)
        try:
            from pywebrtc_audio import EchoCanceller
        except ImportError as exc:
            raise RuntimeError("pywebrtc-audio is unavailable; install it or use --backend linear") from exc
        mask, count, total = select_reference_active(near, far, sample_rate, cfg)
        gain = _gain(near, far, mask)
        echo = EchoCanceller(sample_rate=sample_rate, num_channels=1,
                             stream_delay_ms=int(cfg["webrtc_stream_delay_ms"]))
        # Standalone AEC3 intentionally does not enable AGC or noise suppression.
        residual = np.asarray(echo.process(np.ascontiguousarray(near, dtype=np.float32),
                                           np.ascontiguousarray(far, dtype=np.float32)), dtype=np.float32)
        if len(residual) != len(near):
            raise RuntimeError("WebRTC AEC3 returned an incorrect number of samples")
        db, correlated, leftover = _suppression(near, far, residual, mask, gain)
        status = "ok" if count >= cfg["min_confident_windows"] and db >= cfg["min_reference_suppression_db"] else "cancellation_unreliable"
        warnings = [] if status == "ok" else ["AEC3 did not meet the experimental suppression gate; learner segments suppressed"]
        return CancellationResult(status, residual, "webrtc_aec3", gain, db, correlated, leftover,
                                  int(np.count_nonzero(mask)//max(1,round(cfg["analysis_window_sec"]*sample_rate))), total, warnings)


def cancel_reference(near: np.ndarray, far: np.ndarray, sr: int, cfg: dict) -> CancellationResult:
    backend = cfg["backend"]
    if backend == "linear":
        return LinearCanceller().cancel(near, far, sr, cfg)
    if backend not in ("auto", "webrtc"):
        raise ValueError(f"Unknown cancellation backend: {backend}")
    if backend == "webrtc":
        return WebRTCCanceller().cancel(near, far, sr, cfg)
    return compare_backends(near, far, sr, cfg)[0]
