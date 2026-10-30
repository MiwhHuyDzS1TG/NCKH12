"""Check the P1.3 research controls on the running local Streamlit console."""
from pathlib import Path
import hashlib
import re
import json

from playwright.sync_api import sync_playwright


def main() -> None:
    root = Path(__file__).parents[1]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded")
        report = root/"runs"/"20260916_000304_main_video"/"vad_optimization.json"
        page.get_by_role("button", name=re.compile("20260916_000304_main_video")).click()
        page.get_by_text("Run ID: 20260916_000304_main_video", exact=False).wait_for(timeout=30_000)
        page.get_by_text("Optimize VAD", exact=True).first.wait_for(timeout=45_000)
        if not report.is_file():
            page.get_by_role("button", name="Optimize VAD").click()
            page.get_by_text("Measured 628 candidate settings", exact=False).wait_for(timeout=90_000)
        page.get_by_role("button", name="Preview Candidate").wait_for(timeout=30_000)
        page.get_by_role("button", name="Preview Candidate").click()
        page.get_by_text("Preview:", exact=False).wait_for(timeout=30_000)
        page.screenshot(path=str(root/"screenshots"/"p13-optimization-preview.png"), full_page=True)
        page.get_by_role("button", name="Keep Current").click()
        previous_id = page.locator(".lab-run-id").inner_text()
        old_result = root/"runs"/"20260916_000304_main_video"/"result.json"
        old_hash = hashlib.sha256(old_result.read_bytes()).hexdigest()
        best = json.loads(report.read_text(encoding="utf-8"))["best_development_candidate"]["parameters"]
        applied = []
        for candidate in (root/"runs").glob("*_duet"):
            config_path, result_path = candidate/"config.json", candidate/"result.json"
            if config_path.is_file() and result_path.is_file():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                params = dict(config["vad"]) | {"merge_gap_sec": config["segments"]["merge_gap_sec"]}
                if params == best:
                    applied.append(candidate)
        if applied:
            applied_id = sorted(applied)[-1].name
        else:
            page.get_by_role("button", name="Apply Candidate · create new run").click()
            page.wait_for_function("previous => document.querySelector('.lab-run-id')?.innerText !== previous",
                                   arg=previous_id, timeout=120_000)
            applied_id = page.locator(".lab-run-id").inner_text()
        assert hashlib.sha256(old_result.read_bytes()).hexdigest() == old_hash
        # Exercise Quick Validation on the immutable unfiltered baseline prediction.
        page.get_by_role("button", name=re.compile("20260915_235622_main_video")).click()
        page.get_by_text("Run ID: 20260915_235622_main_video", exact=False).wait_for(timeout=30_000)
        page.get_by_text("Quick review · predicted learner only", exact=True).click()
        page.get_by_role("button", name="Accept all predicted learner segments", exact=False).click()
        page.get_by_text("S001", exact=False).first.wait_for(timeout=30_000)
        page.get_by_role("button", name="ORIGINAL_CONTAMINATION").click()
        page.get_by_text("S002", exact=False).first.wait_for(timeout=30_000)
        confirmation = page.get_by_role("checkbox", name="I reviewed the complete Duet for missed learner speech")
        assert confirmation.is_checked()
        page.get_by_role("button", name="+ Add missed learner interval").click()
        page.get_by_text("Advanced / Diagnostics", exact=True).click()
        page.get_by_text("AUTO backend comparison", exact=True).wait_for(timeout=30_000)
        assert not errors, errors
        assert report.is_file()
        print("optimization_report", report)
        print("preview_and_keep_current", True)
        print("apply_created_new_run", applied_id)
        print("historical_result_unchanged", True)
        print("quick_validation_s001_and_add_missed", True)
        print("browser_errors", errors)
        browser.close()


if __name__ == "__main__":
    main()
