"""Freeze the P2.4 validation technical-eligibility audit before teacher rating."""
from pathlib import Path

from speaking_evidence.p24_validation_preflight import (
    attach_preflight_to_empty_queue,
    build_replacement_manifest,
)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    manifest = build_replacement_manifest(root)
    attach_preflight_to_empty_queue(root)
    print("P2.4 validation scorability preflight frozen")
    print("final queue:", ", ".join(manifest["final_five_ids"]))
    print("technical replacements:", len(manifest["replacements"]))
