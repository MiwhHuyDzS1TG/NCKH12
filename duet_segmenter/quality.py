"""Cheap deterministic audio-quality diagnostics for triage."""
from __future__ import annotations

import numpy as np


def _percentiles(values: np.ndarray, prefix: str) -> dict:
    if values.size == 0:
        return {f"{prefix}_{name}": 0. for name in ("p10", "p50", "p90", "p95")}
    return {f"{prefix}_{name}": float(np.percentile(values, q))
            for name, q in (("p10", 10), ("p50", 50), ("p90", 90), ("p95", 95))}


def measure_audio_quality(audio: np.ndarray, sr: int,
                          learner_segments: list[dict], frame_sec: float = .064) -> dict:
    """Measure level and stationary tonal background without another model."""
    audio = np.asarray(audio, dtype=np.float32)
    width = max(256, int(round(frame_sec*sr)))
    hop = max(128, width//2)
    if len(audio) < width:
        audio = np.pad(audio, (0, width-len(audio)))
    starts = np.arange(0, len(audio)-width+1, hop)
    frames = np.stack([audio[start:start+width] for start in starts])
    windowed = frames*np.hanning(width)[None, :]
    power = np.abs(np.fft.rfft(windowed, axis=1))**2 + 1e-12
    rms = np.sqrt(np.mean(frames*frames, axis=1))
    flatness = np.exp(np.mean(np.log(power), axis=1))/np.mean(power, axis=1)
    # A stable narrow-band background (music or electronic tones) raises this ratio.
    tonality = np.max(power, axis=1)/np.sum(power, axis=1)
    centers = (starts+width/2)/sr
    learner = np.zeros(len(starts), dtype=bool)
    for segment in learner_segments:
        learner |= (centers >= float(segment["start"])) & (centers <= float(segment["end"]))
    background = ~learner
    speech_rms = float(np.median(rms[learner])) if np.any(learner) else 0.
    background_rms = float(np.median(rms[background])) if np.any(background) else 0.
    ratio_db = float(20*np.log10((speech_rms+1e-9)/(background_rms+1e-9)))
    result = {
        "frame_sec": frame_sec,
        "frame_count": int(len(frames)),
        "learner_frame_fraction": float(np.mean(learner)),
        "speech_rms_median": speech_rms,
        "background_rms_median": background_rms,
        "speech_to_background_db": ratio_db,
        "clipping_fraction": float(np.mean(np.abs(audio) >= .99)),
    }
    result.update(_percentiles(rms, "rms"))
    result.update(_percentiles(rms[learner], "speech_rms"))
    result["speech_level_dbfs_median"] = float(20*np.log10(speech_rms)) if speech_rms > 0 else None
    result.update(_percentiles(rms[background], "background_rms"))
    result.update(_percentiles(flatness[background], "background_flatness"))
    result.update(_percentiles(tonality[background], "background_tonality"))
    return result


def background_interference(features: dict, cfg: dict) -> bool:
    """Conservative rule: require both a loud background and poor separation."""
    return bool(
        features["background_rms_p90"] >= cfg["background_rms_p90_min"] and
        features["speech_to_background_db"] <= cfg["speech_to_background_db_max"] and
        features["background_tonality_p90"] >= cfg["background_tonality_p90_min"]
    )


def low_speech_level(features: dict, cfg: dict) -> bool:
    """Conservative development-calibrated weak-recording check."""
    return bool(
        features.get("learner_frame_fraction", 0.) > 0 and
        features["speech_rms_median"] <= cfg["low_speech_rms_median_max"] and
        features["rms_p90"] <= cfg["low_speech_rms_p90_max"] and
        features["speech_to_background_db"] <= cfg["low_speech_to_background_db_max"]
    )
