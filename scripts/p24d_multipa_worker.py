"""Run released MultiPA inference inside the isolated Python 3.9 environment.

This worker deliberately has no training path. It consumes a frozen chunk manifest,
uses the released assessment checkpoint, and writes resumable raw outputs.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--hubert", type=Path, required=True)
    parser.add_argument("--roberta", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--whisper-cache", type=Path, required=True)
    args = parser.parse_args()

    local_hf_cache = args.whisper_cache.parent / "hf_cache"
    os.environ.setdefault("HF_HOME", str(local_hf_cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(local_hf_cache / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(local_hf_cache / "transformers"))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    sys.path.insert(0, str(args.source.resolve()))
    import numpy as np
    import torch
    import torchaudio
    import whisper
    import fairseq
    from Charsiu import charsiu_forced_aligner
    from fairseq.models.roberta import RobertaModel
    from model_assessment import PronunciationPredictor
    from utils_assessment import (
        convert_num_to_word,
        feature_extraction,
        get_transcript,
        remove_pun_except_apostrophe,
    )

    request = json.loads(args.request.read_text(encoding="utf-8"))
    if request.get("mode") != "PRETRAINED_INFERENCE_ONLY":
        raise ValueError("Worker refuses any mode other than pretrained inference")
    if not torch.cuda.is_available():
        raise RuntimeError("Released MultiPA source requires CUDA on this machine")
    device = torch.device("cuda")
    torch.set_grad_enabled(False)

    load_started = time.perf_counter()
    word_model = RobertaModel.from_pretrained(str(args.roberta), checkpoint_file="model.pt")
    word_model.eval()
    whisper_model = whisper.load_model("base.en", device="cpu", download_root=str(args.whisper_cache))
    alignment_model = charsiu_forced_aligner(aligner="charsiu/en_w2v2_fc_10ms")
    ssl_models, _, _ = fairseq.checkpoint_utils.load_model_ensemble_and_task([str(args.hubert)])
    assessment_model = PronunciationPredictor(ssl_models[0], 768, 768).to(device)
    state = torch.load(str(args.checkpoint), map_location=device)
    assessment_model.load_state_dict(state, strict=True)
    assessment_model.eval()
    load_runtime = time.perf_counter() - load_started

    existing = ({"items": []} if not args.output.exists()
                else json.loads(args.output.read_text(encoding="utf-8")))
    completed = {(row["pair_id"], row["chunk_index"]) for row in existing.get("items", [])}
    results = list(existing.get("items", []))
    for item in request["items"]:
        for chunk in item["chunks"]:
            key = (item["pair_id"], chunk["chunk_index"])
            if key in completed:
                continue
            started = time.perf_counter()
            row = {
                "pair_id": item["pair_id"],
                "chunk_index": chunk["chunk_index"],
                "wav_sha256": chunk["wav_sha256"],
                "target_text": chunk["target_text"],
                "target_source": "HUMAN_CONFIRMED_T001_TARGET_SPAN",
                "valid": False,
            }
            try:
                wav, sample_rate = torchaudio.load(chunk["wav_path"])
                if sample_rate != 16000:
                    wav = torchaudio.transforms.Resample(sample_rate, 16000)(wav)
                if wav.shape[0] != 1:
                    wav = torch.mean(wav, dim=0, keepdim=True)
                wav = wav.reshape(-1)
                if wav.numel() >= 16000 * 15:
                    raise ValueError("Frozen adapter produced a chunk >=15 seconds")
                target_text = convert_num_to_word(
                    remove_pun_except_apostrophe(chunk["target_text"]).lower())
                asr_text = convert_num_to_word(
                    remove_pun_except_apostrophe(get_transcript(wav, whisper_model)).lower())
                if not target_text or not asr_text:
                    raise ValueError("Empty target or official Whisper-base transcript")
                (aligned_words, features_p, features_w, phonevector,
                 gt_embed, asr_embed, word_phone_map) = feature_extraction(
                    wav.numpy(), target_text, asr_text,
                    alignment_model=alignment_model, word_model=word_model)
                timesplit = [[(int(float(word[0]) * 16000), int(float(word[1]) * 16000))
                              for word in aligned_words]]
                with torch.no_grad():
                    outputs = assessment_model(
                        wav.to(device).reshape(1, -1),
                        torch.from_numpy(asr_embed).to(device).float().unsqueeze(0),
                        torch.from_numpy(gt_embed).to(device).float().unsqueeze(0),
                        torch.from_numpy(features_p).to(device).float().unsqueeze(0),
                        torch.from_numpy(features_w).to(device).float().unsqueeze(0),
                        torch.from_numpy(phonevector).to(device).float().unsqueeze(0),
                        [word_phone_map], timesplit)
                utterance = [float(value.detach().cpu().numpy()[0]) for value in outputs[:4]]
                word_acc = outputs[4].detach().cpu().numpy()[0].astype(float).tolist()
                word_stress = outputs[5].detach().cpu().numpy()[0].astype(float).tolist()
                aligned_text = [str(word[-1]) for word in aligned_words.tolist()]
                if not all(np.isfinite(utterance)):
                    raise ValueError("Non-finite utterance score")
                row.update({
                    "valid": True,
                    "accuracy": utterance[0],
                    "fluency": utterance[1],
                    "prosody": utterance[2],
                    "total": utterance[3],
                    "word_accuracy": word_acc,
                    "word_stress": word_stress,
                    "word_text": aligned_text,
                    "official_whisper_base_transcript": asr_text,
                    "aligned_target_word_count": len(aligned_text),
                })
            except Exception as exc:  # a failed chunk remains explicit, never receives a score
                row["error"] = f"{type(exc).__name__}: {exc}"
            row["runtime_sec"] = time.perf_counter() - started
            results.append(row)
            _atomic_json(args.output, {
                "version": "P2.4D-MultiPA-raw-v1",
                "mode": "PRETRAINED_INFERENCE_ONLY",
                "device": str(device),
                "model_load_runtime_sec": load_runtime,
                "items": results,
            })
            torch.cuda.empty_cache()
            gc.collect()
            print(f"{item['pair_id']} chunk {chunk['chunk_index']}: "
                  f"{'VALID' if row['valid'] else row.get('error')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
