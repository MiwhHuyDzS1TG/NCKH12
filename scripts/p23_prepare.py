"""Reproduce P2.3 pre-human-rating artifacts without running a final scorer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from speaking_evidence.pronunciation import (build_asr_pronunciation_baseline,
                                              create_rating_schema_v2,
                                              probe_openpronounce)
from speaking_evidence.runner import write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--espeak-root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    ground = root / "human_ground_truth" / "p22a_v1"
    ratings = create_rating_schema_v2(ground / "ratings_v1.json", ground / "ratings_v2.json")
    evidence_root = root / "assessment_runs" / "T001_p22_calibrated_v01"
    baseline = build_asr_pronunciation_baseline(evidence_root,
                                                root / "task_profiles" / "T001_target_text_v1.json")
    backend = probe_openpronounce(args.espeak_root)
    backend.update({"backend": "OpenPronounce", "package_pin": "openpronounce==0.3.0",
                    "human_ratings_used": 0, "holdout_processed": False})
    write_json(root / "calibration" / "p23_pronunciation_v01" /
               "openpronounce_status_v1.json", backend)
    print({"rating_schema": ratings["schema_version"],
           "human_ratings": sum(item["human_confirmed"] is True for item in ratings["items"]),
           "baseline": baseline["status"], "openpronounce": backend["status"],
           "holdout_processed": False})


if __name__ == "__main__":
    main()
