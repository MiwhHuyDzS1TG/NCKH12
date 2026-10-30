"""Optional, independent Community-1 research baseline.

This module is not imported by the main pipeline and does not modify its results.
Loading a Hub model may download weights; pass a local model directory for offline use.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .media import SAMPLE_RATE, normalize_audio


def community_one_diarization(duet_path: str | Path, normalized_wav: str | Path,
                              model: str = "pyannote/speaker-diarization-community-1",
                              token: str | None = None) -> list[dict]:
    """Return two-speaker diarization intervals on the Duet timeline for comparison."""
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError("Optional baseline requires pyannote.audio; it is not installed with duet-segmenter") from exc
    _, audio = normalize_audio(duet_path, normalized_wav)
    pipeline = Pipeline.from_pretrained(model, token=token)
    if pipeline is None:
        raise RuntimeError("Could not load pyannote Community-1; check model access or local model directory")
    input_waveform = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)
    output = pipeline({"waveform": input_waveform, "sample_rate": SAMPLE_RATE}, num_speakers=2)
    diarization = output.speaker_diarization
    return [{"start": float(turn.start), "end": float(turn.end), "speaker": str(speaker)}
            for turn, _, speaker in diarization.itertracks(yield_label=True)]
