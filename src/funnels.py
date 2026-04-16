import re
from urllib.parse import urlparse

from playwright.sync_api import Page

from . import config


def list_funnels(page: Page) -> list[dict]:
    """Return [{id, name, url}, ...] across all pagination pages of /funnels."""
    page.goto(config.FUNNELS_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # After login CF redirects to <workspace>-app.clickfunnels.com — use it.
    parsed = urlparse(page.url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    funnels: dict[str, dict] = {}
    page_num = 1

    while True:
        anchors = page.eval_on_selector_all(
            'a[href*="/funnels/"]',
            "els => els.map(e => ({href: e.getAttribute('href'),"
            " text: (e.innerText || '').trim()}))",
        )
        before = len(funnels)
        for a in anchors:
            href = a.get("href") or ""
            # Only bare /funnels/<id> links (skip /funnels/<id>/stats etc)
            m = re.fullmatch(r"/funnels/(\d+)", href)
            if not m:
                continue
            fid = m.group(1)
            if fid in funnels:
                if not funnels[fid]["name"] and a["text"]:
                    funnels[fid]["name"] = a["text"]
                continue
            funnels[fid] = {
                "id": fid,
                "name": a["text"] or f"funnel-{fid}",
                "url": f"{origin}/funnels/{fid}",
            }
        print(f"[funnels] page {page_num}: +{len(funnels) - before} (total {len(funnels)})")

        next_btn = page.locator(
            'a[rel="next"], a.next_page, nav a:has-text("Next")'
        ).first
        if next_btn.count() == 0 or not next_btn.is_visible():
            break
        try:
            next_btn.click()
            page.wait_for_load_state("networkidle")
            page_num += 1
        except Exception as e:
            print(f"[funnels] pagination stopped: {e}")
            break

    return sorted(funnels.values(), key=lambda f: int(f["id"]))
