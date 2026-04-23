"""Enrich per-funnel sales CSVs with precise purchase timestamps.

Uses direct HTTP requests (with the browser's cookies) instead of full
page.goto to avoid rendering overhead — ~10x faster per contact.
"""

import csv
import json
import re
import time

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page

from . import config

BATCH_SIZE = 50  # flush CSV + state every N contacts


def create_session(page: Page) -> requests.Session:
    """Build a requests.Session that shares the browser's cookies."""
    session = requests.Session()
    for c in page.context.cookies():
        session.cookies.set(
            c["name"], c["value"],
            domain=c.get("domain", ""),
            path=c.get("path", "/"),
        )
    ua = page.evaluate("navigator.userAgent")
    session.headers["User-Agent"] = ua
    return session


def load_enrich_state() -> dict:
    if config.ENRICH_STATE_FILE.exists():
        return json.loads(config.ENRICH_STATE_FILE.read_text())
    return {}


def save_enrich_state(state: dict) -> None:
    config.ENRICH_STATE_FILE.write_text(json.dumps(state, indent=2))


def enrich_funnel_csv(session: requests.Session, funnel_id: str, origin: str) -> int:
    """Add purchase_timestamp to rows in output/<funnel_id>.csv. Returns count updated."""
    csv_path = config.OUTPUT_DIR / f"{funnel_id}.csv"
    if not csv_path.exists():
        print(f"  [{funnel_id}] no CSV at {csv_path} — skipping")
        return 0

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return 0

    state = load_enrich_state()
    done_cids: set[str] = set(state.get(funnel_id, []))

    # Collect unique contact_ids not yet processed
    pending_cids: list[str] = []
    seen_cids: set[str] = set()
    for row in rows:
        cid = (row.get("contact_id") or "").strip()
        if not cid or cid in done_cids or cid in seen_cids:
            continue
        pending_cids.append(cid)
        seen_cids.add(cid)

    if not pending_cids:
        print(f"  [{funnel_id}] nothing to enrich "
              f"(all {len(done_cids)} contacts already processed)")
        return 0

    updated = 0
    batch_count = 0

    for i, cid in enumerate(pending_cids):
        profile, purchases = _fetch_contact_purchases(session, origin, cid)

        for row in rows:
            if (row.get("contact_id") or "").strip() != cid:
                continue
            if profile.get("name"):
                row["customer_name"] = profile["name"]
            if not row.get("email") and profile.get("email"):
                row["email"] = profile["email"]
            if not row.get("purchase_timestamp"):
                match = _match_purchase(row, purchases)
                if match and match.get("timestamp"):
                    row["purchase_timestamp"] = match["timestamp"]
                    updated += 1

        done_cids.add(cid)
        batch_count += 1

        # Flush every BATCH_SIZE contacts
        if batch_count >= BATCH_SIZE:
            state[funnel_id] = list(done_cids)
            save_enrich_state(state)
            _write_csv(csv_path, rows)
            batch_count = 0

        if (i + 1) % 20 == 0 or i == len(pending_cids) - 1:
            print(f"    [{funnel_id}] {i + 1}/{len(pending_cids)} contacts processed")

    # Final flush
    if batch_count > 0:
        state[funnel_id] = list(done_cids)
        save_enrich_state(state)
        _write_csv(csv_path, rows)

    print(f"  [{funnel_id}] enriched {updated}/{len(rows)} rows "
          f"({len(pending_cids)} fetched, {len(done_cids)} total processed)")
    return updated


def _write_csv(csv_path, rows: list[dict]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=config.SALES_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _fetch_contact_purchases(
    session: requests.Session, origin: str, contact_id: str
) -> tuple[dict, list[dict]]:
    """Fetch contact profile + purchases via HTTP. Returns (profile, purchases)."""
    profile: dict = {"name": "", "email": ""}
    all_purchases: list[dict] = []
    page_num = 1

    while True:
        url = f"{origin}/contact_profiles/{contact_id}/purchases?page={page_num}"
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"    [{contact_id}] HTTP {resp.status_code}")
                break
        except requests.RequestException as e:
            print(f"    [{contact_id}] request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract name + email from profile header (first page only)
        if page_num == 1:
            profile = _parse_profile(soup)

        # Extract purchase rows
        purchases = _parse_purchases(soup)
        if not purchases:
            break
        all_purchases.extend(purchases)

        # Check for next page link
        if not soup.select_one('a[rel="next"], li.next:not(.disabled) a'):
            break

        page_num += 1

    return profile, all_purchases


def _parse_profile(soup: BeautifulSoup) -> dict:
    """Extract name and email from the h2.ui.header on the profile page."""
    name = ""
    email = ""
    content_div = soup.select_one("h2.ui.header div.content")
    if content_div:
        # Name is the first direct text node
        for node in content_div.children:
            if isinstance(node, str):
                t = node.strip()
                if t:
                    name = t
                    break
        # Email is in the sub header
        sub = content_div.select_one(".sub.header, .sub")
        if sub:
            email = sub.get_text(strip=True)
    return {"name": name, "email": email}


def _parse_purchases(soup: BeautifulSoup) -> list[dict]:
    """Extract purchase rows from the table."""
    purchases = []
    for tr in soup.select("table tbody tr"):
        cells = [td.get_text(strip=True) for td in tr.select("td")]
        # Precise timestamp from div.ui.small.grey.text (or gray)
        ts_el = tr.select_one(".ui.small.grey.text, .ui.small.gray.text")
        timestamp = ts_el.get_text(strip=True) if ts_el else ""

        # Table columns: Time | Product | Amount | Status | Funnel
        purchases.append({
            "timestamp": timestamp,
            "product": cells[1] if len(cells) > 1 else "",
            "amount": cells[2] if len(cells) > 2 else "",
            "status": cells[3] if len(cells) > 3 else "",
            "funnel": cells[4] if len(cells) > 4 else "",
        })
    return purchases


def _match_purchase(row: dict, purchases: list[dict]) -> dict | None:
    if not purchases:
        return None

    row_prod = _norm(row.get("product", ""))
    row_amt = _num(row.get("amount", ""))

    # 1. Product + amount
    if row_prod and row_amt:
        for p in purchases:
            if _substr_match(row_prod, _norm(p.get("product", ""))) \
               and _amt_eq(row_amt, _num(p.get("amount", ""))):
                return p

    # 2. Product alone
    if row_prod:
        for p in purchases:
            if _substr_match(row_prod, _norm(p.get("product", ""))):
                if not row_amt or _amt_eq(row_amt, _num(p.get("amount", ""))):
                    return p

    # 3. Amount alone
    if row_amt:
        for p in purchases:
            if _amt_eq(row_amt, _num(p.get("amount", ""))):
                return p

    # 4. Single purchase fallback
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
