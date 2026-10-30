"""Diagnostic plots with the same Duet timeline used by JSON predictions."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_alignment(result, path: str | Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), constrained_layout=True)
    axes[0].plot(result.curve_offsets_sec, result.curve_scores, lw=1, color="#365d8d")
    axes[0].axvline(result.coarse_offset_sec, color="#cc4e35", lw=1.5,
                    label=f"coarse peak {result.coarse_offset_sec:.3f} s")
    axes[0].set(xlabel="Duet time minus original time (s)", ylabel="normalized log-Mel correlation",
                title="Coarse reference alignment")
    axes[0].legend(loc="upper right")
    if result.anchors:
        times = np.array([x.original_time for x in result.anchors])
        offsets = np.array([x.best_offset for x in result.anchors])
        correlations = np.array([x.correlation for x in result.anchors])
        scatter = axes[1].scatter(times, offsets, c=correlations, cmap="viridis", vmin=0, vmax=1,
                                  s=75, edgecolors="black", linewidths=0.3)
        for x in result.anchors:
            axes[1].annotate(f"{x.correlation:.2f}", (x.original_time, x.best_offset),
                             xytext=(3, 4), textcoords="offset points", fontsize=8)
        line = np.linspace(min(times), max(times), 100)
        axes[1].plot(line, (result.a-1)*line+result.b, color="#cc4e35", lw=1.3,
                     label=f"offset={result.b:.6f}+({result.a-1:.6g})×t")
        fig.colorbar(scatter, ax=axes[1], label="anchor waveform correlation")
        axes[1].legend(loc="best")
    axes[1].set(xlabel="original anchor time (s)", ylabel="local offset (s)", title="Fine PCM anchors")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_timeline(duration: float, original: list[dict], residual: list[dict],
                  learner: list[dict], overlaps: list[dict], outside: list[dict],
                  template_start: float, template_end: float, path: str | Path) -> None:
    rows = [("Original VAD", original, "#446c9b"), ("Residual VAD", residual, "#e6a355"),
            ("Predicted learner", learner, "#268b75"), ("Overlap candidate", overlaps, "#c25b72"),
            ("Outside template", outside, "#929292")]
    fig, ax = plt.subplots(figsize=(16, 5.6), constrained_layout=True)
    for y, (label, segments, color) in enumerate(rows):
        ax.broken_barh([(s["start"], s["end"]-s["start"]) for s in segments],
                       (y-0.32, 0.64), facecolors=color)
    ax.axvspan(max(0., template_start), min(duration, template_end), color="#e9eee6", zorder=-1,
               label="Mapped template interval")
    ax.axvline(template_end, color="#222", ls="--", lw=1)
    ax.set(xlim=(0, duration), ylim=(-0.6, len(rows)-0.4), xlabel="Duet time (s)",
           yticks=range(len(rows)), yticklabels=[r[0] for r in rows],
           title="Reference-aware Duet learner speech timeline")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="upper right")
    fig.savefig(path, dpi=160)
    plt.close(fig)
