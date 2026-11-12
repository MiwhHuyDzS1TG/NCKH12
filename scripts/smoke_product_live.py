"""Run one genuine private Product V2 assessment through the React surface.

This opt-in smoke re-assesses the most recent user-media item. It never prints
the title, path, transcript, evidence, or score values.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from speaking_evidence.media_library import MediaLibrary


URL = "http://127.0.0.1:8765"
SAFE_SCREENSHOT = ROOT / "ui_evidence/after/processing-genuine-1366.png"
PRIVATE_SCREENSHOT = ROOT / "screenshots/product-ui/processing-genuine-1366.png"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify-saved",
        action="store_true",
        help="Verify the result created by a prior genuine run without assessing again.",
    )
    parser.add_argument(
        "--capture-only",
        action="store_true",
        help="Start a genuine run, capture its real processing state, and return without waiting.",
    )
    args = parser.parse_args()
    items = httpx.get(f"{URL}/api/media", timeout=10).raise_for_status().json()["items"]
    if not items:
        print(json.dumps({"status": "SKIPPED", "reason": "NO_PRIVATE_USER_MEDIA"}))
        return 2
    media_id = items[0]["media_id"]
    page_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        if args.verify_saved:
            page.goto(f"{URL}/results/media/{media_id}", wait_until="networkidle")
        else:
            page.goto(f"{URL}/assess?media={media_id}", wait_until="networkidle")
            page.locator(".analysis-state").wait_for(timeout=60_000)
            PRIVATE_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            SAFE_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=PRIVATE_SCREENSHOT, full_page=True)
            page.add_style_tag(content="""
              .library-info h2, .media-row strong { filter: blur(8px) !important; user-select: none !important; }
              .demo-thumb img, .library-thumb img, .media-row img { filter: blur(24px) !important; }
            """)
            page.locator(".analysis-state").scroll_into_view_if_needed()
            page.screenshot(path=SAFE_SCREENSHOT, full_page=False)
            if args.capture_only:
                print(json.dumps({"status": "PASS", "genuine_processing_state_captured": True}))
                browser.close()
                return 0
            page.wait_for_url(f"**/results/media/{media_id}", timeout=1_200_000)
        page.locator(".overall-practice, .overall-unavailable").wait_for(timeout=30_000)
        browser.close()

    record = MediaLibrary().get(media_id)
    result_path = MediaLibrary().analysis_dir(media_id) / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    feedback_error = result.get("automatic_feedback_error_code")
    assertions = {
        "result_persisted": result_path.is_file(),
        "input_identity_preserved": result.get("raw_duet_sha256") == record.get("sha256"),
        "feedback_serialization_safe": feedback_error != "feedback_serialization_failed",
        "react_results_opened": True,
        "page_traceback_absent": not page_errors,
        "holdout_processed": result.get("holdout_processed") is False,
    }
    print(json.dumps({"status": "PASS" if all(assertions.values()) else "FAIL", **assertions}, indent=2))
    return 0 if all(assertions.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
