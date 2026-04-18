"""ClickFunnels Classic sales scraper.

Prereq: run ./launch_chrome.sh, then log in to ClickFunnels in that Chrome window.

Typical four-step workflow:
    python scrape.py --funnels     # enumerate funnels -> output/funnels.json
    python scrape.py --sales       # scrape each funnel's sales -> per-funnel CSVs
    python scrape.py --enrich      # visit contact profiles to add purchase timestamps
    python scrape.py --upload      # push CSVs to PostgreSQL (needs DB_* in .env)
Or combine steps:
    python scrape.py --funnels --sales --enrich --upload
"""

import argparse
import sys
from urllib.parse import urlparse

from src import browser, config, enrich, funnels, sales, storage, upload


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--funnels", action="store_true",
                    help="Enumerate funnels and save to output/funnels.json")
    ap.add_argument("--sales", action="store_true",
                    help="Scrape sales using the saved funnels list")
    ap.add_argument("--enrich", action="store_true",
                    help="Add purchase_timestamp to each sales CSV via contact profiles")
    ap.add_argument("--upload", action="store_true",
                    help="Upload all per-funnel CSVs to PostgreSQL (needs DB_* in .env)")
    ap.add_argument("--funnel", help="Operate on a single funnel id only")
    ap.add_argument("--limit", type=int, help="Cap number of funnels (testing)")
    ap.add_argument("--no-resume", action="store_true",
                    help="Rescrape funnels even if marked complete in _state.json")
    ap.add_argument("--list-only", action="store_true",
                    help="Enumerate funnels and print them, without saving or scraping")
    args = ap.parse_args()

    # If no step flag was provided, default to --funnels + --sales (enrich/upload are opt-in).
    if not (args.funnels or args.sales or args.enrich or args.upload or args.funnel or args.list_only):
        args.funnels = True
        args.sales = True

    # --funnel <id> on its own means "act on just this funnel" for whatever
    # steps are selected. If no step is selected alongside it, default to --sales.
    if args.funnel and not (args.sales or args.enrich or args.funnels or args.list_only):
        args.sales = True

    storage.ensure_output()
    state = {"completed": []} if args.no_resume else storage.load_state()

    needs_browser = args.funnels or args.sales or args.enrich or args.list_only or args.funnel

    pw = page = origin = None
    if needs_browser:
        pw, _browser, _ctx, page = browser.attach()

    try:
        if needs_browser:
            browser.ensure_logged_in(page)
            parsed = urlparse(page.url)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else config.BASE_URL

            fns = _resolve_funnels(args, page, origin)

            if args.list_only:
                for f in fns:
                    print(f"  {f['id']}\t{f['name']}")
                return

            if args.limit:
                fns = fns[: args.limit]

            if args.sales:
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

            if args.enrich:
                enriched_state = state.setdefault("enriched", [])
                for f in fns:
                    if f["id"] in enriched_state:
                        print(f"[skip-enrich] {f['id']} already enriched")
                        continue
                    print(f"[enrich] {f['id']} — {f['name']}")
                    try:
                        enrich.enrich_funnel_csv(page, f["id"], origin)
                        enriched_state.append(f["id"])
                        storage.save_state(state)
                    except Exception as e:
                        print(f"  [error] {f['id']}: {e}", file=sys.stderr)

            if args.sales or args.enrich:
                total = storage.write_combined()
                print(f"[done] combined CSV: {config.COMBINED_CSV} ({total} rows)")

        if args.upload:
            print("[upload] pushing to PostgreSQL...")
            upload.upload_csvs(funnel_id=args.funnel)
    finally:
        if pw:
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
