"""Run the P1.4b repair on development data only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/".local"/"Lib"/"site-packages"), str(ROOT/".vendor")]

from duet_segmenter.p14b import run_p14b


if __name__ == "__main__":
    result = run_p14b(ROOT/"cohort_runs"/"T001_p14")
    print(json.dumps(result, ensure_ascii=False, indent=2))
