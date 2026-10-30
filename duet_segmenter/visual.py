"""Deterministic template-region matching; never identifies learner faces."""
from __future__ import annotations

from dataclasses import dataclass
import itertools
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np


@dataclass
class VisualAlignment:
    status: str
    template_side: str | None
    a: float
    b: float
    visual_match_score: float
    anchor_mad_sec: float
    accepted_anchor_count: int
    accepted_anchor_coverage: float
    anchors: list[dict]
    side_scores: dict[str, float]
    warnings: list[str]

    def as_dict(self) -> dict:
        return vars(self)


def video_metadata(path: str | Path) -> dict:
    capture = cv2.VideoCapture(str(Path(path)))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    if fps <= 0 or frames <= 0 or width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video metadata: {path}")
    return {"width": width, "height": height, "fps": fps, "frame_count": frames,
            "duration_sec": frames/fps}


def _fingerprint(frame: np.ndarray, size: tuple[int, int] = (32, 56)) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    resized = cv2.resize(gray, size, interpolation=cv2.INTER_AREA).astype(np.float32)
    # Blend intensity and gradients to tolerate normal re-encoding and mild color/filter changes.
    gx = cv2.Sobel(resized, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(resized, cv2.CV_32F, 0, 1, ksize=3)
    feature = np.concatenate([resized.ravel(), .25*np.hypot(gx, gy).ravel()])
    feature -= feature.mean()
    norm = float(np.linalg.norm(feature))
    return feature/max(norm, 1e-8)


def extract_fingerprints(path: str | Path, times: np.ndarray,
                         side: str = "full") -> np.ndarray:
    capture = cv2.VideoCapture(str(Path(path)))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    out = []
    for timestamp in times:
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0., float(timestamp))*1000)
        ok, frame = capture.read()
        if not ok:
            out.append(np.zeros(32*56*2, dtype=np.float32))
            continue
        if side != "full":
            midpoint = frame.shape[1]//2
            frame = frame[:, :midpoint] if side == "left" else frame[:, midpoint:]
        out.append(_fingerprint(frame))
    capture.release()
    return np.asarray(out, dtype=np.float32)


def _normalize_duet_layout(frame: np.ndarray) -> np.ndarray:
    """Remove plain export letterboxing, then normalize the two-panel canvas."""
    if frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    active_columns = np.mean(frame > 10, axis=0) >= .12
    columns = np.flatnonzero(active_columns)
    active_rows = np.mean(frame > 10, axis=1) >= .12
    rows = np.flatnonzero(active_rows)
    if len(columns) >= 4 and len(rows) >= 4:
        first, last = int(columns[0]), int(columns[-1])+1
        top, bottom = int(rows[0]), int(rows[-1])+1
        # Ignore tiny bright overlays in otherwise empty margins.
        if (last-first >= max(8, int(.20*frame.shape[1])) and
                bottom-top >= max(8, int(.20*frame.shape[0]))):
            frame = frame[top:bottom, first:last]
    return cv2.resize(frame, (64, 56), interpolation=cv2.INTER_AREA)


def _split_fingerprints(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    normalized = _normalize_duet_layout(frame)
    return _fingerprint(normalized[:, :32]), _fingerprint(normalized[:, 32:])


def sample_duet(path: str | Path, sample_fps: float) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        metadata = video_metadata(path)
        scaled_width = max(2, 2*round((metadata["width"]*56/metadata["height"])/2))
        proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(Path(path)),
            "-vf", f"fps={sample_fps},scale={scaled_width}:56,format=gray", "-an", "-f", "rawvideo",
            "-pix_fmt", "gray", "-"], capture_output=True, check=False)
        frame_bytes = scaled_width*56
        if proc.returncode == 0 and len(proc.stdout) >= frame_bytes:
            count = len(proc.stdout)//frame_bytes
            frames = np.frombuffer(proc.stdout[:count*frame_bytes], dtype=np.uint8).reshape(count, 56, scaled_width)
            times = np.arange(count, dtype=float)/sample_fps
            split = [_split_fingerprints(frame) for frame in frames]
            left = np.asarray([item[0] for item in split])
            right = np.asarray([item[1] for item in split])
            return times, {"left": left, "right": right}
    capture = cv2.VideoCapture(str(Path(path)))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    step = max(1, round(fps/sample_fps))
    times, left, right = [], [], []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % step == 0:
            left_feature, right_feature = _split_fingerprints(frame)
            times.append(index/fps)
            left.append(left_feature)
            right.append(right_feature)
        index += 1
    capture.release()
    if not times:
        raise RuntimeError(f"No decodable video frames: {path}")
    return np.asarray(times), {"left": np.asarray(left), "right": np.asarray(right)}


def align_fingerprints(anchor_times: np.ndarray, template_features: np.ndarray,
                       duet_times: np.ndarray, side_features: dict[str, np.ndarray],
                       cfg: dict) -> VisualAlignment:
    per_side: dict[str, list[dict]] = {}
    side_scores = {}
    for side, features in side_features.items():
        anchors = []
        for time, fingerprint in zip(anchor_times, template_features):
            candidates = np.flatnonzero(np.abs(duet_times-time) <= cfg["search_sec"])
            if not len(candidates) or not np.any(fingerprint):
                continue
            scores = features[candidates] @ fingerprint
            best_local = int(np.argmax(scores))
            best = int(candidates[best_local])
            anchors.append({"template_time": float(time), "duet_time": float(duet_times[best]),
                            "offset": float(duet_times[best]-time),
                            "score": float(scores[best_local]), "accepted": False})
        per_side[side] = anchors
        side_scores[side] = float(np.median([x["score"] for x in anchors])) if anchors else 0.
    side = max(side_scores, key=side_scores.get) if side_scores else None
    anchors = per_side.get(side, [])
    candidates = [x for x in anchors if x["score"] >= cfg["min_anchor_score"]]
    coverage = 0.
    if len(candidates) >= 2:
        x = np.asarray([row["template_time"] for row in candidates])
        y = np.asarray([row["duet_time"] for row in candidates])
        scores = np.asarray([row["score"] for row in candidates])
        max_scale = float(cfg["max_time_scale_deviation"])
        limit = float(cfg["max_anchor_mad_sec"])
        # Repeated/static frames can produce excellent but wrong endpoint matches. Build a
        # deterministic RANSAC-style consensus from constant-offset and anchor-pair models.
        models = [(1., float(y_i-x_i)) for x_i, y_i in zip(x, y)]
        for first, second in itertools.combinations(range(len(candidates)), 2):
            proposed_a = float((y[second]-y[first])/(x[second]-x[first]))
            if abs(proposed_a-1.) <= max_scale:
                models.append((proposed_a, float(y[first]-proposed_a*x[first])))
        best = None
        full_span = max(float(x.max()-x.min()), 1e-9)
        for proposed_a, proposed_b in models:
            proposed_residual = np.abs(y-(proposed_a*x+proposed_b))
            proposed_keep = proposed_residual <= limit
            if not np.any(proposed_keep):
                continue
            span = ((float(x[proposed_keep].max()-x[proposed_keep].min())/full_span)
                    if np.count_nonzero(proposed_keep) > 1 else 0.)
            rank = (int(np.count_nonzero(proposed_keep)), span,
                    float(scores[proposed_keep].sum()),
                    -float(np.median(proposed_residual[proposed_keep])),
                    -abs(proposed_a-1.))
            if best is None or rank > best[0]:
                best = (rank, proposed_a, proposed_b, proposed_keep)
        _, a, b, keep = best
        # Least-squares refinement is constrained to the allowed export speed range;
        # the median intercept prevents one edge anchor from pulling the whole timeline.
        fitted_a = (float(np.polyfit(x[keep], y[keep], 1)[0])
                    if np.count_nonzero(keep) >= 2 else float(a))
        a = float(np.clip(fitted_a, 1.-max_scale, 1.+max_scale))
        b = float(np.median(y[keep]-a*x[keep]))
        residual = np.abs(y-(a*x+b))
        keep = residual <= limit
        if np.count_nonzero(keep) >= 2:
            b = float(np.median(y[keep]-a*x[keep]))
            signed = y[keep]-(a*x[keep]+b)
            mad = float(np.median(np.abs(signed-np.median(signed))))
            coverage = float(x[keep].max()-x[keep].min())/full_span
            for row, accepted in zip(candidates, keep):
                row["accepted"] = bool(accepted)
        else:
            mad = float("inf")
        accepted = [row for row in candidates if row["accepted"]]
    else:
        a, b, mad, accepted = 1., 0., float("inf"), []
    score = float(np.median([row["score"] for row in accepted])) if accepted else 0.
    reliable = (side is not None and score >= cfg["min_match_score"] and
                len(accepted) >= cfg["min_accepted_anchors"] and
                coverage >= cfg.get("min_anchor_coverage", 0.) and
                mad <= cfg["max_anchor_mad_sec"] and
                abs(float(a)-1.) <= cfg["max_time_scale_deviation"]+1e-9)
    warnings = [] if reliable else ["Visual template alignment is weak or inconsistent"]
    return VisualAlignment("ok" if reliable else "visual_alignment_unreliable", side,
                           float(a), float(b), score, mad, len(accepted), coverage, anchors,
                           side_scores, warnings)


def align_video(anchor_times: np.ndarray, template_features: np.ndarray,
                duet_path: str | Path, cfg: dict) -> VisualAlignment:
    times, features = sample_duet(duet_path, cfg["sample_fps"])
    return align_fingerprints(anchor_times, template_features, times, features, cfg)
