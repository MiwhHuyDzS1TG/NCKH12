"""Run P1.4c only on the frozen V2 development split."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/".local"/"Lib"/"site-packages"), str(ROOT/".vendor")]

from duet_segmenter.p14c import run_p14c


if __name__ == "__main__":
    print(json.dumps(run_p14c(ROOT/"cohort_runs"/"T001_p14"), ensure_ascii=False, indent=2))
