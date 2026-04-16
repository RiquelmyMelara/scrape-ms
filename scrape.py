"""ClickFunnels Classic sales scraper.

Prereq: run ./launch_chrome.sh, then log in to ClickFunnels in that Chrome window.

Typical two-step workflow:
    python scrape.py --funnels     # enumerate funnels -> output/funnels.json
    python scrape.py --sales       # load funnels.json, scrape each funnel's sales
Or both in one run:
    python scrape.py --funnels --sales
"""

import argparse
import sys
from urllib.parse import urlparse

from src import browser, config, funnels, sales, storage


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--funnels", action="store_true",
                    help="Enumerate funnels and save to output/funnels.json")
    ap.add_argument("--sales", action="store_true",
                    help="Scrape sales using the saved funnels list")
    ap.add_argument("--funnel", help="Scrape sales for a single funnel id (implies --sales)")
    ap.add_argument("--limit", type=int, help="Cap number of funnels (testing)")
    ap.add_argument("--no-resume", action="store_true",
                    help="Rescrape funnels even if marked complete in _state.json")
    ap.add_argument("--list-only", action="store_true",
                    help="Enumerate funnels and print them, without saving or scraping")
    args = ap.parse_args()

    # If no step flag was provided, do both (backward-compatible default).
    if not (args.funnels or args.sales or args.funnel or args.list_only):
        args.funnels = True
        args.sales = True

    # --funnel <id> implies we want sales for that one funnel.
    if args.funnel:
        args.sales = True

    storage.ensure_output()
    state = {"completed": []} if args.no_resume else storage.load_state()

    pw, _browser, _ctx, page = browser.attach()
    try:
        browser.ensure_logged_in(page)

        # CF redirects post-login to <workspace>-app.clickfunnels.com; use it.
        parsed = urlparse(page.url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else config.BASE_URL

        fns = _resolve_funnels(args, page, origin)

        if args.list_only:
            for f in fns:
                print(f"  {f['id']}\t{f['name']}")
            return

        if not args.sales:
            return  # --funnels only

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


def _resolve_funnels(args, page, origin: str) -> list[dict]:
    """Return the list of funnels to act on, based on flags."""
    if args.funnel:
        return [{
            "id": args.funnel,
            "name": f"funnel-{args.funnel}",
            "url": f"{origin}/funnels/{args.funnel}",
        }]

    if args.funnels or args.list_only:
        print("[funnels] enumerating...")
        fns = funnels.list_funnels(page)
        print(f"[funnels] total: {len(fns)}")
        if args.funnels:
            storage.save_funnels(fns)
            print(f"[funnels] saved -> {config.FUNNELS_FILE}")
        return fns

    # --sales without --funnels: load from disk.
    fns = storage.load_funnels()
    print(f"[funnels] loaded {len(fns)} from {config.FUNNELS_FILE}")
    return fns


if __name__ == "__main__":
    main()
