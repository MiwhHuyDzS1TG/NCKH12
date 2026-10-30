"""Silero VAD on detection residual and original reference."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VADResult:
    segments: list[dict]
    frame_probabilities: np.ndarray
    frame_sec: float


@dataclass
class ProbabilityCache:
    probabilities: np.ndarray
    sample_count: int
    sample_rate: int = 16_000
    frame_samples: int = 512

    def timestamps(self, cfg: dict) -> VADResult:
        """Apply Silero's default hysteresis/duration/padding rules without model inference."""
        threshold = float(cfg["threshold"])
        negative = max(threshold - 0.15, 0.01)
        min_speech = self.sample_rate * int(cfg["min_speech_duration_ms"]) / 1000
        min_silence = self.sample_rate * int(cfg["min_silence_duration_ms"]) / 1000
        pad = self.sample_rate * int(cfg["speech_pad_ms"]) / 1000
        triggered, temp_end, current = False, 0, {}
        speeches = []
        for index, probability in enumerate(self.probabilities):
            position = self.frame_samples * index
            if probability >= threshold and temp_end:
                temp_end = 0
            if probability >= threshold and not triggered:
                triggered = True
                current = {"start": position}
                continue
            if probability < negative and triggered:
                if not temp_end:
                    temp_end = position
                if position - temp_end < min_silence:
                    continue
                current["end"] = temp_end
                if current["end"] - current["start"] > min_speech:
                    speeches.append(current)
                current, temp_end, triggered = {}, 0, False
        if current and self.sample_count - current["start"] > min_speech:
            current["end"] = self.sample_count
            speeches.append(current)
        for index, speech in enumerate(speeches):
            if index == 0:
                speech["start"] = int(max(0, speech["start"] - pad))
            if index < len(speeches)-1:
                silence = speeches[index+1]["start"] - speech["end"]
                if silence < 2*pad:
                    speech["end"] += int(silence//2)
                    speeches[index+1]["start"] = int(max(0, speeches[index+1]["start"] - silence//2))
                else:
                    speech["end"] = int(min(self.sample_count, speech["end"] + pad))
                    speeches[index+1]["start"] = int(max(0, speeches[index+1]["start"] - pad))
            else:
                speech["end"] = int(min(self.sample_count, speech["end"] + pad))
        return VADResult([{"start": item["start"]/self.sample_rate,
                           "end": item["end"]/self.sample_rate} for item in speeches],
                         self.probabilities, self.frame_samples/self.sample_rate)


class SileroDetector:
    def __init__(self, onnx: bool = True):
        try:
            from silero_vad import load_silero_vad
        except ImportError as exc:
            raise RuntimeError("Silero VAD is required. Install the project dependencies.") from exc
        self.model = load_silero_vad(onnx=onnx)

    def infer(self, audio: np.ndarray, sample_rate: int) -> ProbabilityCache:
        if sample_rate != 16_000 or audio.ndim != 1:
            raise ValueError("Silero VAD expects mono 16 kHz PCM")
        import torch
        x = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))
        self.model.reset_states()
        frame = 512
        probs = []
        with torch.no_grad():
            for start in range(0, len(x), frame):
                chunk = x[start:start+frame]
                if len(chunk) < frame:
                    chunk = torch.nn.functional.pad(chunk, (0, frame-len(chunk)))
                probs.append(float(self.model(chunk, sample_rate).item()))
        return ProbabilityCache(np.asarray(probs, dtype=np.float32), len(audio), sample_rate, frame)

    def detect(self, audio: np.ndarray, sample_rate: int, cfg: dict) -> VADResult:
        return self.infer(audio, sample_rate).timestamps(cfg)


def mean_probability(result: VADResult, start: float, end: float) -> float:
    lo = max(0, int(start/result.frame_sec))
    hi = min(len(result.frame_probabilities), max(lo+1, int(np.ceil(end/result.frame_sec))))
    if lo >= hi:
        return 0.
    return float(np.mean(result.frame_probabilities[lo:hi]))
