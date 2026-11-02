"""Isolated WhisperX alignment worker; never changes canonical ASR evidence."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from pathlib import Path

import whisperx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    device = "cpu"
    started_load = time.perf_counter()
    model, metadata = whisperx.load_align_model(
        language_code="en", device=device,
        model_name=request["align_model"],
        model_dir=request.get("model_dir"),
    )
    load_runtime = time.perf_counter() - started_load
    items = []
    for index, item in enumerate(request["items"], start=1):
        print(f"[P2.4] WhisperX {index}/{len(request['items'])} {item['pair_id']}", flush=True)
        started = time.perf_counter()
        try:
            audio = whisperx.load_audio(item["audio_path"])
            result = whisperx.align(
                item["segments"], model, metadata, audio, device,
                return_char_alignments=False,
            )
            words = []
            for segment in result.get("segments", []):
                for word in segment.get("words", []):
                    words.append({
                        "text": str(word.get("word", "")).strip(),
                        "start": word.get("start"), "end": word.get("end"),
                        "score": word.get("score"),
                    })
            aligned = sum(1 for word in words
                          if word.get("start") is not None and word.get("end") is not None)
            items.append({
                "pair_id": item["pair_id"], "status": "ALIGNMENT_READY",
                "runtime_sec": time.perf_counter() - started,
                "words": words, "aligned_word_count": aligned,
                "unalignable_word_count": len(words) - aligned,
                "canonical_transcript_replaced": False,
                "audio_source": "RAW_COMPLETED_DUET_CROPPED_MASKED",
                "input_sha256": item["input_sha256"], "error": None,
            })
        except Exception as exc:
            items.append({"pair_id": item["pair_id"], "status": "ALIGNMENT_FAILED",
                          "runtime_sec": time.perf_counter() - started, "words": [],
                          "aligned_word_count": 0, "unalignable_word_count": None,
                          "canonical_transcript_replaced": False,
                          "audio_source": "RAW_COMPLETED_DUET_CROPPED_MASKED",
                          "input_sha256": item["input_sha256"],
                          "error": f"{type(exc).__name__}: {exc}"})
    output = {
        "version": "P2.4-whisperx-alignment-v1", "status": "ALIGNMENT_BENCHMARK_COMPLETE",
        "package": f"whisperx=={importlib.metadata.version('whisperx')}",
        "align_model": request["align_model"], "device": device,
        "model_load_runtime_sec": load_runtime, "items": items,
        "canonical_evidence_overwritten": False, "holdout_processed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2,
                                      allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
