"""
Take screenshots of the web UI after each part really runs.

  streamlit run app.py              # in one terminal
  python ui_screenshots.py          # in another: all 4 parts
  python ui_screenshots.py 3 4      # just some parts

Drives your installed Google Chrome with Playwright (no extra browser
download): clicks each tab's button, waits for the agents to finish, and saves
screenshots/ui_partN.png. Every screenshot is a real run against Groq.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
URL = "http://localhost:8501"
WIDTH = 1440
PARTS = {
    1: ("1 · Reply to a pasted email", "Draft reply", "Writer"),
    2: ("2 · Reply to the first email", "Reply to first email", "Writer"),
    3: ("3 · Sort the day's emails", "Sort emails", "Reader"),
    4: ("4 · Sort + draft replies", "Sort and draft replies", "Reader → Writer"),
}


def fit_to_content(page) -> None:
    """Streamlit scrolls inside its own container, so grow the window to fit everything."""
    height = page.evaluate(
        """() => Math.max(...[...document.querySelectorAll('[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main, .main')]
            .map(el => el.scrollHeight), document.body.scrollHeight)"""
    )
    page.set_viewport_size({"width": WIDTH, "height": min(max(height + 40, 900), 6000)})
    page.wait_for_timeout(800)


def main() -> None:
    wanted = [int(a) for a in sys.argv[1:]] or list(PARTS)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": WIDTH, "height": 1000}, device_scale_factor=2)
        page.goto(URL)
        page.get_by_text("Email Agents").first.wait_for(timeout=60_000)

        for n in wanted:
            tab, button, label = PARTS[n]
            print(f"Part {n}: running…", flush=True)
            page.set_viewport_size({"width": WIDTH, "height": 1000})
            page.get_by_role("tab", name=tab).click()
            page.get_by_role("button", name=button).click()
            # Wait for this part's status box to say "done" (or "failed").
            done = page.get_by_text(f"{label} — done", exact=True).or_(page.get_by_text(f"{label} failed"))
            done.first.wait_for(timeout=300_000)
            if page.get_by_text(f"{label} failed").count():
                print(f"Part {n}: FAILED — see the UI; screenshot saved anyway")
            page.wait_for_timeout(1500)
            fit_to_content(page)
            os.makedirs(SHOTS, exist_ok=True)
            out = os.path.join(SHOTS, f"ui_part{n}.png")
            page.screenshot(path=out, full_page=True)
            print(f"Part {n}: saved {out}")
            if n != wanted[-1]:
                time.sleep(30)  # stay under Groq's free-tier tokens-per-minute limit
        browser.close()


if __name__ == "__main__":
    main()
