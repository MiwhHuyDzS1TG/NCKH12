"""Measure aligned reference-audio presence separately from alignment."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

from .alignment import logmel


@dataclass
class AudioPresence:
    audio_state: str
    score: float
    features: dict
    reasons: list[str]

    def as_dict(self) -> dict:
        return {"audio_state": self.audio_state,
                "reference_audio_presence_score": self.score,
                "reference_audio_presence_features": self.features,
                "reasons": self.reasons}


def _correlation(x: np.ndarray, y: np.ndarray) -> float:
    x, y = x.astype(np.float64), y.astype(np.float64)
    x, y = x-x.mean(), y-y.mean()
    return float(abs(np.dot(x, y))/np.sqrt(max(np.dot(x, x)*np.dot(y, y), 1e-18)))


def _gcc_max(x: np.ndarray, y: np.ndarray, max_delay: int) -> float:
    x, y = x.astype(np.float64), y.astype(np.float64)
    n = 1 << int(np.ceil(np.log2(len(x)+len(y))))
    cross = np.fft.rfft(x, n)*np.conj(np.fft.rfft(y, n))
    cross /= np.maximum(np.abs(cross), 1e-12)
    cc = np.fft.irfft(cross, n)
    region = np.r_[cc[-max_delay:], cc[:max_delay+1]]
    return float(min(1., np.max(np.abs(region))))


def _active_mask(length: int, sr: int, mapped_vad: list[dict]) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    for item in mapped_vad:
        lo, hi = max(0, round(item["start"]*sr)), min(length, round(item["end"]*sr))
        mask[lo:hi] = True
    return mask


def _distribution(values: np.ndarray, prefix: str) -> dict:
    """Return stable summaries without discarding intermittent evidence."""
    return {
        f"{prefix}_median": float(np.median(values)),
        f"{prefix}_p75": float(np.percentile(values, 75)),
        f"{prefix}_p90": float(np.percentile(values, 90)),
        f"{prefix}_p95": float(np.percentile(values, 95)),
        f"{prefix}_max": float(np.max(values)),
    }


def _longest_run(flags: np.ndarray) -> int:
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def measure_reference_presence(duet: np.ndarray, reference: np.ndarray, sr: int,
                               mapped_reference_vad: list[dict], cfg: dict) -> AudioPresence:
    mask = _active_mask(len(duet), sr, mapped_reference_vad)
    width = max(round(cfg["window_sec"]*sr), 1024)
    rows = []
    starts = []
    for start in range(0, len(duet)-width+1, width):
        active = mask[start:start+width]
        if np.mean(active) < cfg["min_reference_vad_fraction"]:
            continue
        x = reference[start:start+width]
        y = duet[start:start+width]
        if np.sqrt(np.mean(x*x)) < 1e-4:
            continue
        corr = _correlation(x, y)
        gcc = _gcc_max(x, y, round(cfg["gcc_max_delay_ms"]*sr/1000))
        frequencies, coherence = signal.coherence(x, y, fs=sr, nperseg=512, noverlap=256)
        band = (frequencies >= 250) & (frequencies <= 3800)
        coh = float(np.median(coherence[band])) if np.any(band) else 0.
        lx, ly = logmel(x, sr, .032), logmel(y, sr, .032)
        frames = min(len(lx), len(ly))
        spectral = _correlation(lx[:frames].ravel(), ly[:frames].ravel()) if frames else 0.
        gain = float(np.dot(x, y)/max(np.dot(x, x), 1e-12))
        predicted = gain*x
        explained = float(np.sum(predicted*predicted)/max(np.sum(y*y), 1e-12))
        duet_active = float(np.sqrt(np.mean(y*y)) >= cfg["duet_active_rms"])
        rows.append((corr, gcc, coh, spectral, min(1., explained), duet_active, gain))
        starts.append(start/sr)
    if not rows:
        features = {key: 0. for key in ["raw_waveform_correlation", "gcc_phat_peak",
            "speech_band_coherence", "logmel_similarity", "explained_energy",
            "reference_vad_overlap", "estimated_reference_gain"]} | {"window_count": 0}
        return AudioPresence("REFERENCE_PRESENCE_UNCERTAIN", .5, features,
                             ["No usable reference-active windows"])
    values = np.asarray(rows)
    features = {
        "raw_waveform_correlation": float(np.median(values[:, 0])),
        "gcc_phat_peak": float(np.median(values[:, 1])),
        "speech_band_coherence": float(np.median(values[:, 2])),
        "logmel_similarity": float(np.median(values[:, 3])),
        "explained_energy": float(np.median(values[:, 4])),
        "reference_vad_overlap": float(np.mean(values[:, 5])),
        "estimated_reference_gain": float(np.median(values[:, 6])),
        "window_count": len(rows),
    }
    names = ("raw_waveform_correlation", "gcc_phat_peak", "speech_band_coherence",
             "logmel_similarity", "explained_energy")
    for index, name in enumerate(names):
        features.update(_distribution(values[:, index], name))
    window_scores = (.30*values[:, 0] + .15*values[:, 1] + .20*values[:, 2] +
                     .20*values[:, 3] + .15*np.minimum(1., values[:, 4]*2))
    features.update(_distribution(window_scores, "window_score"))
    strong = np.column_stack((
        values[:, 0] >= cfg["strong_correlation"],
        values[:, 2] >= cfg["strong_coherence"],
        values[:, 3] >= cfg["strong_spectral_similarity"],
        values[:, 4] >= cfg["strong_explained_energy"],
    ))
    required = int(cfg.get("strong_window_min_features", 2))
    reference_like = np.sum(strong, axis=1) >= required
    spectral_local = values[:, 3] >= cfg.get("local_spectral_similarity", .70)
    localized_evidence = reference_like | spectral_local
    for index, name in ((0, "correlation"), (1, "coherence"),
                        (2, "spectral_similarity"), (3, "explained_energy")):
        features[f"fraction_above_strong_{name}"] = float(np.mean(strong[:, index]))
    longest = _longest_run(localized_evidence)
    features.update({
        "reference_like_window_fraction": float(np.mean(reference_like)),
        "reference_like_window_count": int(np.sum(reference_like)),
        "localized_evidence_window_fraction": float(np.mean(localized_evidence)),
        "localized_evidence_window_count": int(np.sum(localized_evidence)),
        "longest_reference_like_run_windows": longest,
        "longest_reference_like_run_sec": float(longest*cfg["window_sec"]),
        "reference_like_windows": [
            {"start": float(start), "end": float(start+cfg["window_sec"]),
             "score": float(window_scores[index]),
             "strong_feature_count": int(np.sum(strong[index]))}
            for index, start in enumerate(starts) if localized_evidence[index]
        ],
    })
    # Independent weak evidence sources must agree; VAD overlap is diagnostic, not decisive.
    score = float(.30*features["raw_waveform_correlation"] +
                  .15*features["gcc_phat_peak"] +
                  .20*features["speech_band_coherence"] +
                  .20*features["logmel_similarity"] +
                  .15*min(1., features["explained_energy"]*2))
    strong_count = sum((features["raw_waveform_correlation"] >= cfg["strong_correlation"],
                        features["speech_band_coherence"] >= cfg["strong_coherence"],
                        features["logmel_similarity"] >= cfg["strong_spectral_similarity"],
                        features["explained_energy"] >= cfg["strong_explained_energy"]))
    clean_local = (features["reference_like_window_fraction"] <=
                   cfg.get("clean_max_reference_like_fraction", 0.) and
                   features["window_score_p95"] <= cfg.get("clean_max_p95_score", .30) and
                   features["logmel_similarity_p95"] <=
                   cfg.get("clean_max_spectral_p95", .58) and
                   features["logmel_similarity_max"] <=
                   cfg.get("clean_max_spectral_max", .60))
    locally_present = (
        features["window_score_p95"] >= cfg.get("local_present_min_score", .45) and
        features["reference_like_window_fraction"] >= cfg.get("local_present_min_fraction", .08) and
        features["longest_reference_like_run_windows"] >=
        int(cfg.get("local_present_min_consecutive_windows", 2))
    )
    globally_present = score >= cfg["reference_present_min_score"] and strong_count >= 2
    spectrally_persistent = (
        features["logmel_similarity_p90"] >= cfg.get("local_spectral_p90_present", .70) and
        features["fraction_above_strong_spectral_similarity"] >=
        cfg.get("local_spectral_fraction_present", .25)
    )
    if score <= cfg["clean_muted_max_score"] and strong_count == 0 and clean_local:
        state, reasons = "CLEAN_MUTED", ["Aligned template audio evidence is consistently negligible"]
    elif globally_present or locally_present or spectrally_persistent:
        state, reasons = "REFERENCE_PRESENT", ["Multiple aligned audio features indicate audible template speech"]
    else:
        state, reasons = "REFERENCE_PRESENCE_UNCERTAIN", ["Reference-audio evidence is borderline or inconsistent"]
    return AudioPresence(state, score, features, reasons)


def contamination_scope(features: dict, learner_segments: list[dict], alignment_ok: bool,
                        audio_state: str = "REFERENCE_PRESENCE_UNCERTAIN") -> str:
    """Locate reference-like evidence relative to scoring candidate regions."""
    windows = features.get("reference_like_windows", [])
    if not alignment_ok:
        return "UNKNOWN"
    if not windows:
        return "NONE" if audio_state == "CLEAN_MUTED" else "UNKNOWN"
    for window in windows:
        if any(min(window["end"], segment["end"]) > max(window["start"], segment["start"])
               for segment in learner_segments):
            return "SCORING_REGION"
    return "INTRO_OR_NONSCORING_ONLY"
