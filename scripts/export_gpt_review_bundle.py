"""Export manual ChatGPT review materials for a frozen competition demo."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speaking_evidence.competition_demo import DEMO_IDS
from speaking_evidence.competition_review import export_review_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video_id", choices=DEMO_IDS)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    destination = export_review_bundle(ROOT, args.video_id, args.destination)
    print(f"GPT review bundle ready: {destination}")
    print("Submit the bundle manually. ChatGPT website automation was not used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
