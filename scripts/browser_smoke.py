"""Local Playwright smoke test and screenshots for the Research Console.

Use after starting Streamlit on 127.0.0.1. --run-analysis creates a real run.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--run-analysis", action="store_true")
    args = parser.parse_args()
    screenshots = Path(__file__).parents[1]/"screenshots"
    screenshots.mkdir(exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 950}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="domcontentloaded")
        page.locator('[data-testid="stMetric"]').first.wait_for(timeout=45_000)
        before_run = page.locator(".lab-run-id").inner_text()
        if args.run_analysis:
            page.get_by_role("button", name="Run Analysis").click()
            page.wait_for_function("previous => document.querySelector('.lab-run-id')?.innerText !== previous",
                                   arg=before_run, timeout=120_000)
            page.locator('[data-testid="stMetric"]').first.wait_for(timeout=45_000)
        page.screenshot(path=str(screenshots/"research-console-overview.png"))
        chart = page.locator('[data-testid="stPlotlyChart"]')
        chart.wait_for(timeout=45_000)
        chart.screenshot(path=str(screenshots/"research-console-timeline.png"))
        assert "OUTSIDE_TEMPLATE" in chart.inner_text()
        review = page.locator('[data-testid="stDataFrame"]').first
        review.screenshot(path=str(screenshots/"research-console-review.png"))
        assert page.locator('[data-testid="stMetric"]').count() >= 15
        learner_card = page.locator('[data-testid="stMetric"]').filter(has_text="Learner segments")
        assert learner_card.count() == 1 and "21" in learner_card.inner_text()
        assert page.locator('[data-testid="stAudio"]').count() >= 1
        page.get_by_text("±0.5 s context", exact=True).click()
        caption = page.get_by_text("From unprocessed Duet source audio", exact=False).inner_text()
        assert "44,100 Hz" in caption and "2 channel(s)" in caption
        page.get_by_text("Completed Duet video", exact=True).click()
        assert page.locator('[data-testid="stVideo"]').count() >= 1
        assert not errors, errors
        print("title", page.title())
        print("run_id", page.locator(".lab-run-id").inner_text())
        print("summary_has_21", True)
        print("audio_caption", caption)
        print("browser_errors", errors)
        print("screenshots", [str(p) for p in sorted(screenshots.glob("research-console-*.png"))])
        browser.close()


if __name__ == "__main__":
    main()
