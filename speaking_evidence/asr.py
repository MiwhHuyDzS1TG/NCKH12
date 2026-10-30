"""Lazy local ASR interface and faster-whisper implementation."""
from __future__ import annotations

import re
import time
from importlib.metadata import version
from pathlib import Path
from typing import Protocol


def normalize_transcript(text: str) -> str:
    """Whitespace only: never repair a learner's grammar or remove repetitions."""
    return re.sub(r"\s+", " ", text).strip()


def validate_words(words: list[dict], start: float, end: float) -> None:
    previous = start
    for word in words:
        left, right = float(word["start_sec"]), float(word["end_sec"])
        if left < previous - 0.02 or right < left or left < start - 0.02 or right > end + 0.02:
            raise ValueError("ASR words must be monotonic and inside their learner turn")
        previous = left


class ASRBackend(Protocol):
    def transcribe(self, audio_path: Path, timeline_start: float,
                   timeline_end: float, intervals: list[dict]) -> dict: ...


class FasterWhisperBackend:
    def __init__(self, model: str = "small.en", language: str = "en", beam_size: int = 5,
                 device: str = "auto", compute_type: str = "auto"):
        from faster_whisper import WhisperModel

        self.auto_device = device == "auto"
        if device == "auto":
            try:
                import ctranslate2
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        self.model = WhisperModel(model, device=device, compute_type=compute_type)
        self.model_name, self.language, self.beam_size = model, language, beam_size
        self.device, self.compute_type = device, compute_type
        self.version = version("faster-whisper")

    def transcribe(self, audio_path: Path, timeline_start: float,
                   timeline_end: float, intervals: list[dict]) -> dict:
        try:
            return self._transcribe_once(audio_path, timeline_start, timeline_end, intervals)
        except RuntimeError as exc:
            # A GPU can be enumerated while its CUDA runtime DLLs are absent.
            if not self.auto_device or self.device != "cuda" or not any(
                part in str(exc).lower() for part in ("cuda", "cublas", "cudnn")):
                raise
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            self.device, self.compute_type = "cpu", "int8"
            return self._transcribe_once(audio_path, timeline_start, timeline_end, intervals)

    def _transcribe_once(self, audio_path: Path, timeline_start: float,
                         timeline_end: float, intervals: list[dict]) -> dict:
        started = time.perf_counter()
        stream, info = self.model.transcribe(str(audio_path), language=self.language,
                                              beam_size=self.beam_size, word_timestamps=True,
                                              condition_on_previous_text=False,
                                              vad_filter=False)
        segments, words = [], []
        for segment in stream:
            segments.append({"text": segment.text, "start_sec": timeline_start + segment.start,
                             "end_sec": timeline_start + segment.end,
                             "avg_logprob": segment.avg_logprob,
                             "no_speech_prob": segment.no_speech_prob})
            for word in segment.words or []:
                left, right = timeline_start + word.start, timeline_start + word.end
                midpoint = (left + right) / 2
                if not any(i["start"] - 0.02 <= midpoint <= i["end"] + 0.02 for i in intervals):
                    continue
                if left < timeline_start - 0.02 or right > timeline_end + 0.02:
                    continue
                words.append({"text": word.word, "start_sec": round(left, 3),
                              "end_sec": round(right, 3),
                              "probability": getattr(word, "probability", None)})
        words.sort(key=lambda w: (w["start_sec"], w["end_sec"]))
        validate_words(words, timeline_start, timeline_end)
        verbatim = "".join(w["text"] for w in words).strip()
        return {"segments": segments, "words": words,
                "verbatim_transcript": verbatim,
                "normalized_transcript": normalize_transcript(verbatim),
                "runtime_sec": round(time.perf_counter() - started, 3),
                "language_probability": getattr(info, "language_probability", None)}

    def provenance(self) -> dict:
        return {"backend": "faster_whisper", "model": self.model_name,
                "version": self.version, "language": self.language,
                "beam_size": self.beam_size, "word_timestamps": True,
                "device": self.device, "compute_type": self.compute_type}
