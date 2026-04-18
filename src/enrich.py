"""Enrich per-funnel sales CSVs with precise purchase timestamps.

For each row that has a `contact_id`, visit
    /contact_profiles/<id>/purchases
and pull the timestamp for the purchase that matches the row.
Also backfills customer_name and email from the profile header.
"""

import csv
import random
import re
import time

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

    updated = 0

    for i, cid in enumerate(pending_cids):
        profile, purchases = _fetch_contact_purchases(page, origin, cid)

        # Update ALL rows for this contact
        for row in rows:
            if (row.get("contact_id") or "").strip() != cid:
                continue
            # Always set customer_name from profile — it's the authoritative
            # source. The sales step's pick("name") often matches a wrong
            # column (e.g. "Product Name") and fills in junk.
            if profile.get("name"):
                row["customer_name"] = profile["name"]
            if not row.get("email") and profile.get("email"):
                row["email"] = profile["email"]
            # Match and fill timestamp
            if not row.get("purchase_timestamp"):
                match = _match_purchase(row, purchases)
                if match and match.get("timestamp"):
                    row["purchase_timestamp"] = match["timestamp"]
                    updated += 1

        # Flush to disk after every contact so progress survives interrupts
        _write_csv(csv_path, rows)

        print(f"    [{funnel_id}] contact {i + 1}/{len(pending_cids)} "
              f"(id={cid}, name={profile.get('name', '?')}, "
              f"purchases={len(purchases)})")
        time.sleep(random.uniform(0.4, 1.2))

    print(f"  [{funnel_id}] enriched {updated}/{len(rows)} rows "
          f"({len(pending_cids)} contact profiles fetched)")
    return updated


def _write_csv(csv_path, rows: list[dict]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _fetch_contact_purchases(
    page: Page, origin: str, contact_id: str
) -> tuple[dict, list[dict]]:
    """Return (profile_info, purchases_list) for a contact.

    profile_info: {name, email}
    purchases_list: [{timestamp, product, amount, status, funnel}, ...]
    """
    profile: dict = {"name": "", "email": ""}
    all_purchases: list[dict] = []
    page_num = 1

    while True:
        url = f"{origin}/contact_profiles/{contact_id}/purchases?page={page_num}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception as e:
            print(f"    [{contact_id}] goto failed: {e}")
            return profile, all_purchases

        # Extract name + email from profile header (first page only)
        if page_num == 1:
            profile = page.evaluate("""() => {
                const contentDiv = document.querySelector('h2.ui.header div.content');
                let name = '';
                let email = '';
                if (contentDiv) {
                    // Name is the first text node inside div.content
                    for (const node of contentDiv.childNodes) {
                        if (node.nodeType === 3) {
                            const t = node.textContent.trim();
                            if (t) { name = t; break; }
                        }
                    }
                    // Email is in div.sub.header (or just below the name)
                    const sub = contentDiv.querySelector('.sub.header, .sub');
                    if (sub) email = sub.textContent.trim();
                }
                return {name, email};
            }""")

        # Extract purchase rows
        try:
            page.wait_for_selector("table tbody tr", timeout=10_000)
        except Exception:
            break

        raw = page.eval_on_selector_all(
            "table tbody tr",
            """rows => rows.map(r => {
                const cells = Array.from(r.querySelectorAll('td'));
                // Precise timestamp lives in div.ui.small.grey.text inside first td
                const tsEl = r.querySelector('.ui.small.grey.text, .ui.small.gray.text');
                return {
                    cells: cells.map(td => (td.innerText || '').trim()),
                    timestamp: tsEl ? tsEl.textContent.trim() : ''
                };
            })""",
        )

        if not raw:
            break

        # Table columns: Time | Product | Amount | Status | Funnel
        for row_data in raw:
            cells = row_data["cells"]
            all_purchases.append({
                "timestamp": row_data["timestamp"],
                "product": cells[1] if len(cells) > 1 else "",
                "amount": cells[2] if len(cells) > 2 else "",
                "status": cells[3] if len(cells) > 3 else "",
                "funnel": cells[4] if len(cells) > 4 else "",
            })

        # Pagination: check for a "next" link
        has_next = page.locator(
            'a[rel="next"], li.next:not(.disabled) a, a.next_page'
        ).first
        if has_next.count() == 0 or not has_next.is_visible():
            break

        page_num += 1
        time.sleep(random.uniform(0.3, 0.8))

    return profile, all_purchases


def _match_purchase(row: dict, purchases: list[dict]) -> dict | None:
    """Find the purchase from the contact profile that matches a sales row."""
    if not purchases:
        return None

    row_prod = _norm(row.get("product", ""))
    row_amt = _num(row.get("amount", ""))
    row_funnel = _norm(row.get("funnel_name", ""))

    # 1. Product + amount + funnel (tightest)
    if row_prod and row_amt:
        for p in purchases:
            p_prod = _norm(p.get("product", ""))
            p_amt = _num(p.get("amount", ""))
            if _substr_match(row_prod, p_prod) and _amt_eq(row_amt, p_amt):
                return p

    # 2. Product + amount (no funnel)
    if row_prod:
        for p in purchases:
            p_prod = _norm(p.get("product", ""))
            if _substr_match(row_prod, p_prod):
                if not row_amt or _amt_eq(row_amt, _num(p.get("amount", ""))):
                    return p

    # 3. Amount alone
    if row_amt:
        for p in purchases:
            p_amt = _num(p.get("amount", ""))
            if _amt_eq(row_amt, p_amt):
                return p

    # 4. Fallback: single purchase = assume it's the one
    if len(purchases) == 1:
        return purchases[0]

    return None


def _substr_match(a: str, b: str) -> bool:
    return bool(a and b and (a in b or b in a))


def _amt_eq(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) < 0.01


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _num(s: str) -> float | None:
    m = re.search(r"[\d]+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group(0)) if m else None
