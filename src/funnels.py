import random
import re
import time
from urllib.parse import urlparse

from playwright.sync_api import Page

from . import config


FUNNELS_PER_PAGE = 96  # CF's max on /funnels


def list_funnels(page: Page) -> list[dict]:
    """Return [{id, name, url}, ...] across all pagination pages of /funnels."""
    # Navigate once to resolve the workspace subdomain post-login.
    page.goto(config.FUNNELS_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    parsed = urlparse(page.url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    funnels: dict[str, dict] = {}
    page_num = 1

    while True:
        url = f"{origin}/funnels?page={page_num}&per_page={FUNNELS_PER_PAGE}"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        anchors = page.eval_on_selector_all(
            'a[href*="/funnels/"]',
            "els => els.map(e => ({href: e.getAttribute('href'),"
            " text: (e.innerText || '').trim()}))",
        )

        before = len(funnels)
        found_on_page: set[str] = set()
        for a in anchors:
            href = a.get("href") or ""
            # Only bare /funnels/<id> links (skip /funnels/<id>/stats etc)
            m = re.fullmatch(r"/funnels/(\d+)", href)
            if not m:
                continue
            fid = m.group(1)
            found_on_page.add(fid)
            if fid in funnels:
                if not funnels[fid]["name"] and a["text"]:
                    funnels[fid]["name"] = a["text"]
                continue
            funnels[fid] = {
                "id": fid,
                "name": a["text"] or f"funnel-{fid}",
                "url": f"{origin}/funnels/{fid}",
            }

        added = len(funnels) - before
        print(
            f"[funnels] page {page_num}: +{added} new "
            f"(found {len(found_on_page)} on page, total {len(funnels)})"
        )

        # Stop when this page has fewer than per_page funnels OR added nothing
        # new (CF clamps out-of-range page numbers to the last valid page).
        if len(found_on_page) < FUNNELS_PER_PAGE or added == 0:
            break

        page_num += 1
        time.sleep(random.uniform(0.5, 1.5))

    return sorted(funnels.values(), key=lambda f: int(f["id"]))
