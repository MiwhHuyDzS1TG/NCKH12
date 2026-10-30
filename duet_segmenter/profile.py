"""Reusable template preprocessing for a same-template Duet cohort."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .media import SAMPLE_RATE, normalize_audio
from .vad import SileroDetector
from .visual import extract_fingerprints, video_metadata


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class TemplateProfile:
    directory: Path
    profile: dict
    anchor_times: np.ndarray
    visual_fingerprints: np.ndarray
    reference_audio: np.ndarray
    reference_vad: list[dict]

    @property
    def template_id(self) -> str:
        return self.profile["template_id"]


def build_template_profile(template_path: str | Path, output_dir: str | Path,
                           template_id: str, config: dict, force: bool = False) -> TemplateProfile:
    source = Path(template_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    profile_path = output/"profile.json"
    source_hash = _hash_file(source)
    if profile_path.exists() and not force:
        current = json.loads(profile_path.read_text(encoding="utf-8"))
        if current.get("template_sha256") == source_hash:
            return load_template_profile(output)
    output.mkdir(parents=True, exist_ok=True)
    info, reference = normalize_audio(source, output/"normalized_reference.wav")
    video = video_metadata(source)
    duration = min(info.duration_sec, video["duration_sec"])
    margin = min(2., max(.25, duration*.05))
    anchor_times = np.linspace(margin, max(margin, duration-margin),
                               int(config["visual"]["anchor_count"]))
    fingerprints = extract_fingerprints(source, anchor_times, "full")
    np.savez_compressed(output/"visual_fingerprints.npz", anchor_times=anchor_times,
                        fingerprints=fingerprints)
    detector = SileroDetector()
    vad = detector.infer(reference, SAMPLE_RATE).timestamps(config["vad"])
    (output/"reference_vad.json").write_text(json.dumps(vad.segments, indent=2)+"\n", encoding="utf-8")
    metadata = {"source_path": str(source), "audio": info.as_dict(), "video": video}
    (output/"metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    profile = {"profile_version": 1, "template_id": template_id,
               "template_sha256": source_hash, "duration_sec": duration,
               "anchor_count": len(anchor_times), "sample_rate": SAMPLE_RATE,
               "known_intro_sec": None, "known_outro_sec": None}
    profile_path.write_text(json.dumps(profile, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return TemplateProfile(output, profile, anchor_times, fingerprints, reference, vad.segments)


def load_template_profile(directory: str | Path) -> TemplateProfile:
    directory = Path(directory).expanduser().resolve()
    profile = json.loads((directory/"profile.json").read_text(encoding="utf-8"))
    visual = np.load(directory/"visual_fingerprints.npz")
    reference, sr = sf.read(directory/"normalized_reference.wav", dtype="float32")
    if sr != SAMPLE_RATE:
        raise ValueError("Template profile reference must be 16 kHz")
    vad = json.loads((directory/"reference_vad.json").read_text(encoding="utf-8"))
    return TemplateProfile(directory, profile, visual["anchor_times"], visual["fingerprints"],
                           reference, vad)
