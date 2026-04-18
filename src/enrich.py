"""Enrich per-funnel sales CSVs with precise purchase timestamps.

For each row that has a `contact_id`, visit
    /contact_profiles/<id>/purchases
and pull the timestamp for the purchase that matches the row
(by order_id if present, otherwise by product + amount).
"""

import csv
import random
import re
import time
from urllib.parse import urlparse

from playwright.sync_api import Page

from . import config


def enrich_funnel_csv(page: Page, funnel_id: str, origin: str) -> int:
    """Add `purchase_timestamp` to rows in output/<funnel_id>.csv. Returns count updated."""
    csv_path = config.OUTPUT_DIR / f"{funnel_id}.csv"
    if not csv_path.exists():
        print(f"  [{funnel_id}] no CSV at {csv_path} — skipping")
        return 0

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return 0

    # Collect unique contact_ids that still need enrichment
    pending_cids: list[str] = []
    seen_cids: set[str] = set()
    for row in rows:
        if row.get("purchase_timestamp"):
            continue
        cid = (row.get("contact_id") or "").strip()
        if cid and cid not in seen_cids:
            pending_cids.append(cid)
            seen_cids.add(cid)

    if not pending_cids:
        print(f"  [{funnel_id}] nothing to enrich")
        return 0

    contact_cache: dict[str, list[dict]] = {}
    updated = 0

    for i, cid in enumerate(pending_cids):
        purchases = _fetch_contact_purchases(page, origin, cid)
        contact_cache[cid] = purchases

        # Update ALL rows for this contact
        for row in rows:
            if row.get("purchase_timestamp"):
                continue
            if (row.get("contact_id") or "").strip() != cid:
                continue
            match = _match_purchase(row, purchases)
            if match and match.get("timestamp"):
                row["purchase_timestamp"] = match["timestamp"]
                updated += 1

        # Flush to disk after every contact so progress survives interrupts
        _write_csv(csv_path, rows)

        print(f"    [{funnel_id}] contact {i + 1}/{len(pending_cids)} "
              f"(id={cid}, matched={bool(purchases)})")
        time.sleep(random.uniform(0.4, 1.2))

    print(f"  [{funnel_id}] enriched {updated}/{len(rows)} rows "
          f"({len(contact_cache)} contact profiles fetched)")
    return updated


def _write_csv(csv_path, rows: list[dict]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _fetch_contact_purchases(page: Page, origin: str, contact_id: str) -> list[dict]:
    """Return [{order_id, product, amount, timestamp, raw_cells}, ...] for a contact."""
    url = f"{origin}/contact_profiles/{contact_id}/purchases"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_load_state("networkidle", timeout=20_000)
    except Exception as e:
        print(f"    [{contact_id}] goto failed: {e}")
        return []

    try:
        page.wait_for_selector("table tbody tr", timeout=10_000)
    except Exception:
        return []

    headers = page.eval_on_selector_all(
        "table thead th",
        "ths => ths.map(th => (th.innerText || '').trim().toLowerCase())",
    )
    raw = page.eval_on_selector_all(
        "table tbody tr",
        "rows => rows.map(r => Array.from(r.querySelectorAll('td'))"
        ".map(td => (td.innerText || '').trim()))",
    )

    purchases = []
    for cells in raw:
        by_hdr = dict(zip(headers, cells)) if headers else {}

        def pick(*keys: str) -> str:
            for k in keys:
                for h, v in by_hdr.items():
                    if k in h:
                        return v
            return ""

        purchases.append({
            "order_id": pick("order", "#", " id"),
            "product": pick("product", "item", "name"),
            "amount": pick("amount", "total", "price"),
            # Prefer full timestamp column ("created at", "purchased at", "date")
            "timestamp": pick("created at", "purchased at", "timestamp", "date at", "date"),
            "raw": cells,
        })
    return purchases


def _match_purchase(row: dict, purchases: list[dict]) -> dict | None:
    if not purchases:
        return None

    # 1. Exact order_id match
    oid = (row.get("order_id") or "").strip()
    if oid:
        for p in purchases:
            if p.get("order_id") and p["order_id"].strip() == oid:
                return p

    # 2. Product + amount match (loose: substring/normalized)
    prod = _norm(row.get("product", ""))
    amt = _num(row.get("amount", ""))
    if prod or amt:
        for p in purchases:
            p_prod = _norm(p.get("product", ""))
            p_amt = _num(p.get("amount", ""))
            if prod and p_prod and (prod in p_prod or p_prod in prod):
                if not amt or not p_amt or abs(amt - p_amt) < 0.01:
                    return p

    # 3. Amount alone
    if amt:
        for p in purchases:
            p_amt = _num(p.get("amount", ""))
            if p_amt and abs(amt - p_amt) < 0.01:
                return p

    # 4. Fallback: if the contact only has one purchase, assume it's the one
    if len(purchases) == 1:
        return purchases[0]

    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _num(s: str) -> float | None:
    m = re.search(r"[\d]+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group(0)) if m else None
