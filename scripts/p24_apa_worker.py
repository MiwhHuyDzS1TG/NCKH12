"""Extract official-method pooled SSL-FT-PRON embeddings on CPU."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from pathlib import Path

import numpy as np
import psutil
import soundfile as sf
import torch
from transformers import AutoConfig, AutoFeatureExtractor, HubertModel, Wav2Vec2Model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    candidate = request["candidate"]
    model_class = Wav2Vec2Model if candidate["architecture"] == "wav2vec2" else HubertModel
    started_load = time.perf_counter()
    config = AutoConfig.from_pretrained(candidate["base_model"])
    extractor = AutoFeatureExtractor.from_pretrained(candidate["base_model"])
    model = model_class.from_pretrained(
        candidate["repository"], subfolder=candidate["subfolder"],
        revision=candidate["revision"], config=config, use_safetensors=True,
    )
    model.eval().to("cpu")
    load_runtime = time.perf_counter() - started_load
    process = psutil.Process()
    peak_rss = process.memory_info().rss
    items = []
    embedding_dir = args.output.parent / f"{candidate['candidate_id']}_embeddings"
    embedding_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(request["items"], start=1):
        print(f"[P2.4] {candidate['candidate_id']} {index}/{len(request['items'])} {item['pair_id']}",
              flush=True)
        started = time.perf_counter()
        try:
            audio, rate = sf.read(item["audio_path"], dtype="float32")
            if rate != 16_000 or audio.ndim != 1:
                raise ValueError("APA input must be mono 16 kHz")
            chunk_samples = 15 * rate
            pooled_chunks, chunk_weights = [], []
            with torch.inference_mode():
                for begin in range(0, len(audio), chunk_samples):
                    chunk = audio[begin:begin + chunk_samples]
                    if len(chunk) < int(0.25 * rate):
                        continue
                    inputs = extractor(chunk, sampling_rate=rate, return_tensors="pt")
                    hidden = model(inputs.input_values).last_hidden_state
                    pooled_chunks.append(hidden.mean(dim=1).squeeze(0).cpu().numpy().astype(np.float32))
                    chunk_weights.append(len(chunk))
                    peak_rss = max(peak_rss, process.memory_info().rss)
            if not pooled_chunks:
                raise ValueError("No valid APA chunks")
            embedding = np.average(np.stack(pooled_chunks), axis=0,
                                   weights=np.asarray(chunk_weights, dtype=float))
            destination = embedding_dir / f"{item['pair_id']}.npz"
            np.savez_compressed(destination, mean_pooled_embedding=embedding)
            items.append({
                "pair_id": item["pair_id"], "status": "PRETRAINED_EMBEDDING_FEATURE_READY",
                "embedding_ref": str(destination).replace("\\", "/"),
                "embedding_dimensions": int(len(embedding)), "chunk_count": len(pooled_chunks),
                "runtime_sec": time.perf_counter() - started,
                "input_sha256": item["input_sha256"],
                "audio_source": "RAW_COMPLETED_DUET_CROPPED_MASKED",
                "direct_pretrained_score": None,
                "output_type": "PRETRAINED_EMBEDDING_FEATURE",
                "error": None,
            })
        except Exception as exc:
            items.append({"pair_id": item["pair_id"], "status": "BACKEND_ITEM_FAILED",
                          "embedding_ref": None, "runtime_sec": time.perf_counter() - started,
                          "input_sha256": item["input_sha256"],
                          "audio_source": "RAW_COMPLETED_DUET_CROPPED_MASKED",
                          "direct_pretrained_score": None,
                          "output_type": "PRETRAINED_EMBEDDING_FEATURE",
                          "error": f"{type(exc).__name__}: {exc}"})
    output = {
        "version": "P2.4-ssl-ft-pron-embedding-v1", "candidate": candidate,
        "status": "EMBEDDING_EXTRACTION_COMPLETE",
        "official_method": "last-hidden-state temporal mean pooling",
        "resource_adaptation": "15-second chunk mean pooling, duration-weighted across chunks",
        "scoring_head_available": False, "direct_pretrained_scores_emitted": False,
        "model_load_runtime_sec": load_runtime,
        "total_item_runtime_sec": sum(item["runtime_sec"] for item in items),
        "peak_process_ram_bytes": peak_rss, "device": "cpu", "dtype": "float32",
        "package_versions": {"torch": torch.__version__,
                             "transformers": importlib.metadata.version("transformers")},
        "items": items, "holdout_processed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2,
                                      allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
