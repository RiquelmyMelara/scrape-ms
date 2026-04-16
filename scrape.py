"""ClickFunnels Classic sales scraper.

Prereq: run ./launch_chrome.sh, then log in to ClickFunnels in that Chrome window.
"""

import argparse
import sys
from urllib.parse import urlparse

from src import browser, config, funnels, sales, storage


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--funnel", help="Scrape only this funnel id")
    ap.add_argument("--limit", type=int, help="Cap number of funnels (testing)")
    ap.add_argument("--no-resume", action="store_true", help="Rescrape completed funnels")
    ap.add_argument("--list-only", action="store_true", help="Enumerate funnels and exit")
    args = ap.parse_args()

    storage.ensure_output()
    state = {"completed": []} if args.no_resume else storage.load_state()

    pw, _browser, _ctx, page = browser.attach()
    try:
        browser.ensure_logged_in(page)

        # CF redirects post-login to <workspace>-app.clickfunnels.com; use it.
        parsed = urlparse(page.url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else config.BASE_URL

        if args.funnel:
            fns = [{
                "id": args.funnel,
                "name": f"funnel-{args.funnel}",
                "url": f"{origin}/funnels/{args.funnel}",
            }]
        else:
            print("[funnels] enumerating...")
            fns = funnels.list_funnels(page)
            print(f"[funnels] total: {len(fns)}")

        if args.list_only:
            for f in fns:
                print(f"  {f['id']}\t{f['name']}")
            return

        if args.limit:
            fns = fns[: args.limit]

        for f in fns:
            if f["id"] in state["completed"]:
                print(f"[skip] {f['id']} already scraped")
                continue
            print(f"[scrape] {f['id']} — {f['name']}")
            try:
                rows = sales.scrape_funnel_sales(page, f)
                storage.write_rows(f["id"], rows)
                state["completed"].append(f["id"])
                storage.save_state(state)
            except Exception as e:
                print(f"  [error] {f['id']}: {e}", file=sys.stderr)

        total = storage.write_combined()
        print(f"[done] combined CSV: {config.COMBINED_CSV} ({total} rows)")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
