"""Media probing, FFmpeg normalization, and WAV I/O."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaInfo:
    path: str
    duration_sec: float
    audio_codec: str
    audio_sample_rate: int
    audio_channels: int

    def as_dict(self) -> dict:
        return vars(self)


def _binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name} is required on PATH. Install FFmpeg and verify {name} --version.")
    return found


def _run(args: list[str], label: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise MediaError(f"Cannot launch {label}: {exc}") from exc
    if proc.returncode:
        raise MediaError(f"{label} failed (exit {proc.returncode}): {proc.stderr.strip()[-1500:]}")
    return proc


def probe(path: str | Path) -> MediaInfo:
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise MediaError(f"Input file does not exist: {path}")
    proc = _run([_binary("ffprobe"), "-v", "error", "-show_entries",
                 "format=duration:stream=codec_type,codec_name,sample_rate,channels",
                 "-of", "json", str(path)], f"FFprobe on {path.name}")
    try:
        data = json.loads(proc.stdout)
        duration = float(data["format"]["duration"])
        streams = [s for s in data["streams"] if s.get("codec_type") == "audio"]
        if duration <= 0 or not np.isfinite(duration):
            raise ValueError("duration must be positive")
        if not streams:
            raise MediaError(f"No audio stream in {path}")
        audio = streams[0]
        return MediaInfo(str(path), duration, audio.get("codec_name", "unknown"),
                         int(audio.get("sample_rate", 0)), int(audio.get("channels", 0)))
    except (KeyError, ValueError, TypeError) as exc:
        raise MediaError(f"Invalid or missing duration/audio metadata in {path}: {exc}") from exc


def normalize_audio(source: str | Path, destination: str | Path) -> tuple[MediaInfo, np.ndarray]:
    info = probe(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
          "-i", info.path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
          "-c:a", "pcm_s16le", str(destination)], f"FFmpeg extraction of {Path(source).name}")
    try:
        audio, sample_rate = sf.read(destination, dtype="float32", always_2d=False)
    except (OSError, RuntimeError) as exc:
        raise MediaError(f"Cannot read normalized WAV {destination}: {exc}") from exc
    if audio.ndim != 1 or sample_rate != SAMPLE_RATE or len(audio) == 0:
        raise MediaError(f"Invalid normalized audio in {destination}: expected nonempty 16 kHz mono WAV")
    if not np.all(np.isfinite(audio)):
        raise MediaError(f"Non-finite audio samples in {destination}")
    return info, audio


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.asarray(audio, dtype=np.float32), sample_rate, subtype="PCM_16")


def extract_duet_source_audio(source: str | Path, destination: str | Path) -> tuple[np.ndarray, int]:
    """Decode the Duet audio at its native channels/rate for listening and later scoring."""
    info = probe(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run([_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", info.path,
          "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le", str(destination)],
         f"FFmpeg native-rate audio extraction of {Path(source).name}")
    audio, sample_rate = sf.read(destination, dtype="float32", always_2d=False)
    if len(audio) == 0 or sample_rate <= 0:
        raise MediaError(f"No decoded Duet samples in {destination}")
    return audio, sample_rate
