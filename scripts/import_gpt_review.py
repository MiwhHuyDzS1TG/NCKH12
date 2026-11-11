"""Strictly import a manually obtained ChatGPT competition review."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speaking_evidence.competition_review import import_review


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review_json", type=Path)
    parser.add_argument("--video-id")
    args = parser.parse_args()
    destination = import_review(ROOT, args.review_json, args.video_id)
    print(f"Validated review imported: {destination}")
    print("Official numeric scores were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
