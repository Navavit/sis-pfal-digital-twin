"""Keep the Streamlit Community Cloud app awake: open it in a headless browser (a plain HTTP request does not count as
a visit), press "Yes, get this app back up!" if it has gone to sleep, and wait until the app has rendered.
Run by .github/workflows/keep_awake.yml;  by hand:  pip install playwright && playwright install chromium
                                                     python scripts/keep_awake.py [URL]"""
import re
import sys
import time

from playwright.sync_api import TimeoutError as PwTimeout, sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://sis-pfal-digital-twin.streamlit.app/"
READY_TEXT = "SIS PFAL Digital Twin"      # title of the Overview page
WAKE_BUTTON = re.compile(r"get this app back up", re.I)


def app_rendered(page) -> bool:
    """The app runs inside an iframe on streamlit.app; look for its title there (not in the outer page, which also
    hosts the sleep screen)."""
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        try:
            if fr.get_by_text(READY_TEXT).count():
                return True
        except Exception:
            pass
    return False


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
    woke = False
    t0 = time.time()
    while time.time() - t0 < 600:                       # a cold start can take a few minutes
        btn = page.get_by_role("button", name=WAKE_BUTTON)
        if not woke and btn.count():
            btn.first.click()
            woke = True
            print("app was asleep -> wake-up requested")
        elif app_rendered(page):
            break
        time.sleep(5)
    else:
        browser.close()
        sys.exit(f"app did not render within 10 min ({URL})")
    print(f"app is up ({'woken' if woke else 'was awake'}, {time.time() - t0:.0f} s)")
    try:
        page.wait_for_timeout(20_000)                   # stay a moment so the session counts as a visit
    except PwTimeout:
        pass
    browser.close()
