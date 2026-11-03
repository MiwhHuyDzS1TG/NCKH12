"""Apply the researcher-confirmed D006/D023 technical exclusions safely."""
from pathlib import Path

from speaking_evidence.p24_validation_correction import (
    build_corrected_manifest,
    rebuild_empty_blocked_queue,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    manifest = build_corrected_manifest(root)
    rebuild_empty_blocked_queue(root)
    print("Excluded:", ", ".join(manifest["excluded_ids"]))
    print("Eligible retained queue:", ", ".join(manifest["final_queue_ids"]))
    print("Replacement pool exhausted; teacher validation is blocked at 0/5")
