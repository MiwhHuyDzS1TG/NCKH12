"""Small descriptive pitch/intensity evidence from raw-derived learner audio."""
from __future__ import annotations

import numpy as np


def measure_acoustic(audio: np.ndarray, sample_rate: int, pitch_floor: float = 75,
                     pitch_ceiling: float = 500) -> dict:
    if not 0 < pitch_floor < pitch_ceiling:
        raise ValueError("Invalid pitch range")
    import parselmouth

    if len(audio) < sample_rate * 0.1:
        return {"available": False, "reason": "TOO_SHORT"}
    sound = parselmouth.Sound(audio.astype(float), sampling_frequency=sample_rate)
    pitch = sound.to_pitch(time_step=0.01, pitch_floor=pitch_floor,
                           pitch_ceiling=pitch_ceiling).selected_array["frequency"]
    valid = pitch[np.isfinite(pitch) & (pitch > 0)]
    intensity = sound.to_intensity(time_step=0.01).values.ravel()
    intensity = intensity[np.isfinite(intensity) & (intensity > 0)]
    if not len(valid):
        return {"available": False, "reason": "NO_VOICED_FRAMES",
                "voiced_fraction": 0.0, "pitch_floor_hz": pitch_floor,
                "pitch_ceiling_hz": pitch_ceiling}
    reference = float(np.median(valid))
    semitones = 12 * np.log2(valid / reference)
    return {"available": True, "voiced_fraction": round(len(valid) / len(pitch), 4),
            "f0_median_hz": round(reference, 2),
            "f0_p10_hz": round(float(np.percentile(valid, 10)), 2),
            "f0_p90_hz": round(float(np.percentile(valid, 90)), 2),
            "f0_range_semitones": round(float(np.percentile(semitones, 90) - np.percentile(semitones, 10)), 2),
            "f0_std_semitones": round(float(np.std(semitones)), 2),
            "intensity_median_db": round(float(np.median(intensity)), 2) if len(intensity) else None,
            "intensity_std_db": round(float(np.std(intensity)), 2) if len(intensity) else None,
            "pitch_floor_hz": pitch_floor, "pitch_ceiling_hz": pitch_ceiling}
