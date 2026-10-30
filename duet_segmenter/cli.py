"""Command-line interface."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from .pipeline import load_config, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="duet-segment", description="Detect learner speaking intervals in a completed Duet")
    parser.add_argument("--original", required=True, help="original/template video")
    parser.add_argument("--duet", required=True, help="completed Duet video")
    parser.add_argument("--output", default="output", help="output directory")
    parser.add_argument("--config", help="optional YAML overrides of packaged experimental defaults")
    parser.add_argument("--backend", choices=["auto", "webrtc", "linear"], help="reference cancellation backend")
    parser.add_argument("--ground-truth", help="optional start,end,label CSV")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    try:
        config = load_config(args.config)
        if args.backend:
            config["cancellation"]["backend"] = args.backend
        result = run(args.original, args.duet, args.output, config, args.ground_truth)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        logging.error("%s", exc)
        return 1
    print(json.dumps({"status": result["status"], "estimated_offset_sec": result["alignment_diagnostics"]["b"],
                      "learner_segments": len(result["learner_segments"]),
                      "overlap_candidates": len(result["overlap_candidates"]),
                      "output": result["artifacts"]["result.json"]}, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
