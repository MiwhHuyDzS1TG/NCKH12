"""Smoke-check the populated P1.4 cohort dashboard in a local browser."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    root = Path(__file__).parents[1]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8501", wait_until="domcontentloaded")
        page.get_by_text("Cohort P1.4", exact=True).click()
        page.get_by_text("Cohort triage and scorability", exact=False).wait_for(timeout=45_000)
        page.get_by_text("TOTAL DUETS", exact=True).wait_for(timeout=45_000)
        metric_labels = page.locator('[data-testid="stMetricLabel"]').all_inner_texts()
        assert "TOTAL DUETS" in metric_labels
        assert "SCORABLE CLEAN" in metric_labels
        assert "HUMAN REVIEW" in metric_labels
        page.get_by_text("Triage and quality gates are engineering predictions", exact=False).wait_for()
        page.get_by_text("Minimal audio-state calibration", exact=False).click()
        page.wait_for_timeout(1_000)
        assert page.get_by_text("Human label", exact=True).count() >= 1
        page.get_by_text("Deterministic Green audit", exact=False).click()
        page.wait_for_timeout(1_000)
        assert page.get_by_text("Audit", exact=True).count() >= 1
        assert page.locator("video").count() >= 1
        assert page.locator("audio").count() >= 2
        screenshot = root/"screenshots"/"p14-cohort-dashboard.png"
        page.screenshot(path=str(screenshot), full_page=True)
        assert not errors, errors
        print("metric_count", len(metric_labels))
        print("video_count", page.locator("video").count())
        print("audio_count", page.locator("audio").count())
        print("screenshot", screenshot)
        print("browser_errors", errors)
        browser.close()


if __name__ == "__main__":
    main()
