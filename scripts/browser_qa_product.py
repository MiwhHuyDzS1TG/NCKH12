"""Interaction, motion, responsive and accessibility smoke for DUET / SPEAK."""
from __future__ import annotations

import json

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8765"


def main() -> int:
    checks: dict[str, bool] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768})
        page.goto(URL, wait_until="networkidle")
        page.keyboard.press("Tab")
        checks["keyboard_focus_reaches_control"] = page.evaluate(
            "['A','BUTTON','INPUT','SELECT'].includes(document.activeElement?.tagName)"
        )
        card = page.locator(".demo-card").first
        card.scroll_into_view_if_needed()
        before = card.evaluate("node => getComputedStyle(node).transform")
        card.hover()
        page.wait_for_timeout(260)
        after = card.evaluate("node => getComputedStyle(node).transform")
        checks["media_hover_motion"] = before != after

        page.goto(f"{URL}/assess", wait_until="networkidle")
        zone = page.locator(".upload-zone")
        zone.dispatch_event("dragenter")
        checks["upload_drag_state"] = "dragging" in (zone.get_attribute("class") or "")

        page.goto(f"{URL}/results/demo/T001-D043", wait_until="networkidle")
        feature = page.locator(".criterion-feature")
        feature.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        checks["result_reveal_settles"] = float(feature.evaluate("node => getComputedStyle(node).opacity")) == 1.0
        trigger = page.get_by_role("button", name="Explore the evidence")
        trigger.focus()
        page.keyboard.press("Enter")
        checks["evidence_keyboard_toggle"] = page.get_by_text("Learner transcript").is_visible()

        page.goto(f"{URL}/assess?presenter=1", wait_until="networkidle")
        page.get_by_role("button", name="Presenter controls").click()
        checks["dialog_focus_trapped"] = page.evaluate(
            "Boolean(document.activeElement?.closest('[role=dialog]'))"
        )
        page.keyboard.press("Escape")
        checks["dialog_escape_closes"] = page.locator("[role=dialog]").count() == 0

        reduced = browser.new_context(reduced_motion="reduce", viewport={"width": 390, "height": 844})
        reduced_page = reduced.new_page()
        reduced_page.goto(f"{URL}/assess", wait_until="networkidle")
        checks["reduced_motion_media_query"] = reduced_page.evaluate(
            "matchMedia('(prefers-reduced-motion: reduce)').matches"
        )
        duration = reduced_page.locator(".upload-zone").evaluate(
            "node => getComputedStyle(node).transitionDuration"
        )
        checks["reduced_motion_collapses_transitions"] = duration in {"0s", "1e-05s", "0.00001s"}
        checks["mobile_no_horizontal_overflow"] = reduced_page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth"
        )
        reduced.close()
        browser.close()

    print(json.dumps(checks, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
