import random
import re
import time
from urllib.parse import urlparse

from playwright.sync_api import Page

from . import config


# Classic CF sales view. stats=alltime is REQUIRED (otherwise the page defaults
# to a narrow timeframe and shows zero rows). per_page=100 is the max CF honors.
PER_PAGE = 100
SALES_PATH_TMPL = (
    "/funnels/{fid}/contact_purchases"
    "?page={page}&per_page={per_page}&product_name=&stats=alltime"
)


def scrape_funnel_sales(page: Page, funnel: dict) -> list[dict]:
    """Scrape all sales rows for a funnel using URL-based pagination."""
    # Use the funnel URL's origin (workspace subdomain), not the generic one.
    parsed = urlparse(funnel["url"])
    origin = f"{parsed.scheme}://{parsed.netloc}"

    all_rows: list[dict] = []
    seen: set[str] = set()
    page_num = 1

    while True:
        url = origin + SALES_PATH_TMPL.format(
            fid=funnel["id"], page=page_num, per_page=PER_PAGE
        )
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        try:
            page.wait_for_selector("table tbody tr", timeout=10_000)
        except Exception:
            print(f"  [{funnel['id']}] page {page_num}: no table — stopping")
            break

        headers = page.eval_on_selector_all(
            "table thead th",
            "ths => ths.map(th => (th.innerText || '').trim().toLowerCase())",
        )
        # Extract cells + any per-row link to /contact_profiles/<id>/...
        raw_rows = page.eval_on_selector_all(
            "table tbody tr",
            """rows => rows.map(r => ({
                cells: Array.from(r.querySelectorAll('td'))
                    .map(td => (td.innerText || '').trim()),
                contactHref: (() => {
                    const a = r.querySelector('a[href*="/contact_profiles/"]');
                    return a ? a.getAttribute('href') : '';
                })()
            }))""",
        )

        if not raw_rows:
            print(f"  [{funnel['id']}] page {page_num}: 0 rows — stopping")
            break

        added = 0
        for row_data in raw_rows:
            record = _map_row(row_data["cells"], headers, funnel)
            if not record:
                continue
            record["contact_id"] = _extract_contact_id(row_data.get("contactHref", ""))
            key = record.get("order_id") or f"{funnel['id']}-p{page_num}-{added}"
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(record)
            added += 1

        print(
            f"  [{funnel['id']}] page {page_num}: +{added} rows "
            f"(fetched {len(raw_rows)}, total {len(all_rows)})"
        )

        # Stop conditions:
        #   - fewer than PER_PAGE rows on the page => last page
        #   - nothing new added (likely CF clamped page number and returned same set)
        if len(raw_rows) < PER_PAGE or added == 0:
            break

        page_num += 1
        time.sleep(random.uniform(0.5, 1.5))

    return all_rows


def _extract_contact_id(href: str) -> str:
    m = re.search(r"/contact_profiles/(\d+)", href or "")
    return m.group(1) if m else ""


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
