"""Capture and audit the packaged DUET / SPEAK product at required viewports."""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


URL = "http://127.0.0.1:8765"
PRIVATE_OUTPUT = Path("screenshots/product-ui")
SAFE_OUTPUT = Path("ui_evidence/after")


def layout_audit(page: Page) -> dict:
    return page.evaluate(
        """() => ({
          viewport: {width: innerWidth, height: innerHeight},
          document_width: document.documentElement.scrollWidth,
          document_height: document.documentElement.scrollHeight,
          horizontal_overflow: document.documentElement.scrollWidth > innerWidth,
          clipped_controls: [...document.querySelectorAll('button,a,input,select')].filter((node) => {
            const r = node.getBoundingClientRect();
            return r.width > 0 && r.height > 0 && (node.scrollWidth > node.clientWidth + 2);
          }).map((node) => (node.textContent || node.getAttribute('aria-label') || '').trim()).slice(0, 10),
          missing_images: [...document.images].filter((image) => !image.complete || image.naturalWidth === 0).length,
        })"""
    )


def safe_style(page: Page) -> None:
    page.add_style_tag(content="""
      .demo-thumb img, .library-thumb img, .media-row img { filter: blur(22px) saturate(.35) !important; transform: scale(1.08) !important; }
      .library-info h2, .media-row strong, .connection-state p { filter: blur(7px) !important; user-select: none !important; }
      .passage-block.transcript p { filter: blur(7px) !important; user-select: none !important; }
      .media-stage video { visibility: hidden !important; }
      .media-stage { background: #070b14 !important; border-radius: 5px 32px 32px 32px; min-height: 320px; }
    """)


def capture(page: Page, name: str, *, full_page: bool = True, safe: bool = True) -> dict:
    page.wait_for_timeout(650)
    page.screenshot(path=PRIVATE_OUTPUT / f"{name}.png", full_page=full_page)
    if safe:
        safe_style(page)
        page.screenshot(path=SAFE_OUTPUT / f"{name}.png", full_page=full_page)
    return layout_audit(page)


def settle_results_reveal(page: Page) -> None:
    """Trigger the genuine in-view reveal before a full-document capture."""
    page.locator(".criterion-feature").scroll_into_view_if_needed()
    page.wait_for_timeout(550)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(150)


def main() -> int:
    PRIVATE_OUTPUT.mkdir(parents=True, exist_ok=True)
    SAFE_OUTPUT.mkdir(parents=True, exist_ok=True)
    audits = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height, key in ((1920, 1080, "1920"), (1440, 900, "1440"), (1366, 768, "1366"), (390, 844, "mobile")):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(URL, wait_until="networkidle")
            page.get_by_role("heading", name="Every Duet is a chance to grow.").wait_for()
            audits[f"home_{key}"] = capture(page, f"home-{key}")
            page.close()

        for width, height, key in ((1366, 768, "1366"), (390, 844, "mobile")):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{URL}/assess", wait_until="networkidle")
            page.get_by_role("heading", name="Bring in a completed Duet. We will listen for the learner.").wait_for()
            audits[f"assessment_{key}"] = capture(page, f"assessment-{key}")
            page.close()

        for pair_id, key in (("T001-D043", "d043"), ("T001-D064", "d064"), ("T001-D048", "d048")):
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{URL}/results/demo/{pair_id}", wait_until="networkidle")
            page.get_by_role("heading", name="Overall Practice Score").wait_for()
            settle_results_reveal(page)
            audits[f"results_{key}"] = capture(page, f"results-{key}-1440")
            page.close()

        for width, height, key, full_page in ((1920, 1080, "1920", True), (1366, 768, "1366", False), (768, 1024, "tablet", True), (390, 844, "mobile", True)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"{URL}/results/demo/T001-D043", wait_until="networkidle")
            page.get_by_role("heading", name="Overall Practice Score").wait_for()
            settle_results_reveal(page)
            audits[f"results_{key}"] = capture(page, f"results-d043-{key}", full_page=full_page)
            page.close()

        evidence = browser.new_page(viewport={"width": 1366, "height": 900})
        evidence.goto(f"{URL}/results/demo/T001-D043", wait_until="networkidle")
        evidence.get_by_role("heading", name="Overall Practice Score").wait_for()
        settle_results_reveal(evidence)
        evidence.get_by_role("button", name=re.compile("Explore the evidence")).click()
        evidence.get_by_text("Learner transcript").wait_for()
        audits["evidence_expanded"] = capture(evidence, "evidence-expanded-1366")
        evidence.close()

        library = browser.new_page(viewport={"width": 1440, "height": 900})
        library.goto(f"{URL}/recent", wait_until="networkidle")
        library.get_by_role("heading", name="Recent Videos").wait_for()
        audits["recent_1440"] = capture(library, "recent-1440")
        library.close()

        presenter = browser.new_page(viewport={"width": 1366, "height": 768})
        presenter.goto(f"{URL}/assess?presenter=1", wait_until="networkidle")
        presenter.get_by_role("button", name="Presenter controls").click()
        presenter.get_by_role("heading", name="Personalized feedback connection").wait_for()
        audits["presenter_settings"] = capture(presenter, "presenter-chatgpt-1366", full_page=False)
        presenter.close()
        browser.close()

    print(json.dumps(audits, indent=2))
    if any(row["horizontal_overflow"] or row["missing_images"] for row in audits.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
