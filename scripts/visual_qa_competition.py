"""Capture and mechanically audit the competition UI at presentation sizes."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8501/?mode=competition_demo"
OUTPUT = Path("screenshots")


def audit(page) -> dict:
    return page.evaluate("""
        () => ({
          viewport_width: window.innerWidth,
          document_width: document.documentElement.scrollWidth,
          document_height: document.documentElement.scrollHeight,
          horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth,
          score_cards: [...document.querySelectorAll('.demo-score-card')].map((node) => ({
            width: Math.round(node.getBoundingClientRect().width),
            height: Math.round(node.getBoundingClientRect().height),
            clipped: node.scrollWidth > node.clientWidth || node.scrollHeight > node.clientHeight,
          })),
          feedback_top: Math.round(document.querySelector('.demo-feedback-grid').getBoundingClientRect().top),
          feedback_card_clipping: [...document.querySelectorAll('.demo-feedback-card')].some(
            (node) => node.scrollWidth > node.clientWidth || node.scrollHeight > node.clientHeight
          ),
        })
    """)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(URL)
        page.get_by_role("button", name="Try a Demo").wait_for(timeout=60_000)
        page.screenshot(path=OUTPUT / "competition-home-1366.png")
        results["home_1366"] = page.evaluate(
            "() => ({viewport_width: innerWidth, document_width: document.documentElement.scrollWidth, "
            "horizontal_overflow: document.documentElement.scrollWidth > innerWidth})")
        page.get_by_role("button", name="Try a Demo").click()
        page.get_by_role("button", name="View genuine results").wait_for(timeout=60_000)
        page.screenshot(path=OUTPUT / "competition-assessment-1366.png")
        page.get_by_role("button", name="View genuine results").click()
        page.get_by_text("Your feedback").wait_for(timeout=60_000)
        page.screenshot(path=OUTPUT / "competition-results-1366.png")
        page.screenshot(path=OUTPUT / "competition-results-full-1366.png", full_page=True)
        results["results_1366"] = audit(page)
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.wait_for_timeout(500)
        page.screenshot(path=OUTPUT / "competition-results-1920.png")
        results["results_1920"] = audit(page)
        browser.close()
    print(json.dumps(results, indent=2))
    if any(result.get("horizontal_overflow") for result in results.values()):
        return 1
    if any(card.get("clipped") for key in ("results_1366", "results_1920")
           for card in results[key]["score_cards"]):
        return 1
    if any(results[key]["feedback_card_clipping"] for key in ("results_1366", "results_1920")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
