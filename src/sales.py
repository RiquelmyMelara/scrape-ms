import random
import re
import time
from urllib.parse import urlparse

from playwright.sync_api import Page

from . import config


# Classic CF sales view. The stats=alltime query param is REQUIRED — without
# it the page defaults to a narrow timeframe and shows zero rows.
SALES_PATH = "/contact_purchases?product_name=&stats=alltime"


def scrape_funnel_sales(page: Page, funnel: dict) -> list[dict]:
    """Scrape all sales rows for a funnel across all pagination pages."""
    # Use the funnel URL's origin (workspace subdomain), not the generic one.
    parsed = urlparse(funnel["url"])
    origin = f"{parsed.scheme}://{parsed.netloc}"
    url = f"{origin}/funnels/{funnel['id']}{SALES_PATH}"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    all_rows: list[dict] = []
    seen: set[str] = set()
    page_num = 1

    while True:
        try:
            page.wait_for_selector("table tbody tr", timeout=10_000)
        except Exception:
            print(f"  [{funnel['id']}] no sales table on page {page_num} — stopping")
            break

        headers = page.eval_on_selector_all(
            "table thead th",
            "ths => ths.map(th => (th.innerText || '').trim().toLowerCase())",
        )
        raw_rows = page.eval_on_selector_all(
            "table tbody tr",
            "rows => rows.map(r => Array.from(r.querySelectorAll('td'))"
            ".map(td => (td.innerText || '').trim()))",
        )

        added = 0
        for cells in raw_rows:
            record = _map_row(cells, headers, funnel)
            if not record:
                continue
            key = record.get("order_id") or f"{funnel['id']}-p{page_num}-{added}"
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(record)
            added += 1

        print(f"  [{funnel['id']}] page {page_num}: +{added} rows (total {len(all_rows)})")

        next_btn = page.locator(
            'a[rel="next"], a.next_page, nav a:has-text("Next")'
        ).first
        if next_btn.count() == 0 or not next_btn.is_visible():
            break
        try:
            next_btn.click()
            page.wait_for_load_state("networkidle")
            page_num += 1
            time.sleep(random.uniform(0.5, 1.5))
        except Exception as e:
            print(f"  [{funnel['id']}] pagination stopped: {e}")
            break

    return all_rows


def _map_row(cells: list[str], headers: list[str], funnel: dict) -> dict | None:
    if not cells:
        return None
    by_hdr = dict(zip(headers, cells)) if headers else {}

    def pick(*keys: str) -> str:
        for k in keys:
            for h, v in by_hdr.items():
                if k in h:
                    return v
        return ""

    amount_raw = pick("amount", "total", "price")
    currency = ""
    amount = amount_raw
    m = re.match(r"\s*([^\d\-.,\s]+)?\s*([\d.,]+)", amount_raw or "")
    if m:
        currency = (m.group(1) or "").strip()
        amount = m.group(2) or amount_raw

    return {
        "order_id": pick("order", "#", " id"),
        "date": pick("date", "created"),
        "customer_name": pick("name", "customer"),
        "email": pick("email"),
        "product": pick("product", "item"),
        "amount": amount,
        "currency": currency,
        "status": pick("status", "state"),
        "funnel_id": funnel["id"],
        "funnel_name": funnel["name"],
    }
