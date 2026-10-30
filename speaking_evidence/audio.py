"""Deterministic model input derived exclusively from the raw completed Duet."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_raw_source(source: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if "residual" in source.name.lower() or "cancel" in source.name.lower():
        raise ValueError("Detection/cancellation audio cannot be a canonical Phase-2 source")
    if source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".wav", ".m4a"}:
        raise ValueError("Unsupported raw Duet source type")


def prepare_turn_audio(source: Path, turn: dict, destination: Path,
                       sample_rate: int = 16_000) -> np.ndarray:
    require_raw_source(source)
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg is required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    duration = turn["end_sec"] - turn["start_sec"]
    command = [executable, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
               "-ss", f"{turn['start_sec']:.6f}", "-t", f"{duration:.6f}",
               "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sample_rate),
               "-c:a", "pcm_s16le", str(destination)]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode:
        raise RuntimeError(f"Raw Duet audio extraction failed: {proc.stderr[-500:]}")
    audio, rate = sf.read(destination, dtype="float32")
    if rate != sample_rate or audio.ndim != 1 or not np.isfinite(audio).all():
        raise ValueError("Invalid model-input audio")
    # Mask the space outside Phase-1 learner candidates. ASR sees only candidates,
    # while source-timeline gaps and word offsets remain intact.
    mask = np.zeros(len(audio), dtype=bool)
    for interval in turn["learner_intervals"]:
        begin = max(0, round((interval["start"] - turn["start_sec"]) * rate))
        end = min(len(audio), round((interval["end"] - turn["start_sec"]) * rate))
        mask[begin:end] = True
    audio[~mask] = 0
    sf.write(destination, audio, rate, subtype="PCM_16")
    return audio
