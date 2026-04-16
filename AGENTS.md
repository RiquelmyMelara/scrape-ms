# AGENTS.md

Operating guide for AI coding agents working on this repo.

## What this project is

A Playwright scraper that attaches to a logged-in Chrome session (via CDP) and
extracts sales data from **ClickFunnels Classic** — one CSV per funnel, plus a
combined CSV.

The *shape* of the scraper is done. The *selectors* are best-effort and will
almost certainly need tuning the first time you run against a real account.
Plan to iterate.

## Non-negotiables

1. **Never commit `.env`.** It contains real ClickFunnels credentials. The
   `.gitignore` already excludes it; don't undo that.
2. **Don't change the output schema** (`SALES_FIELDS` in `src/config.py`)
   casually — downstream CSVs depend on it. Extending is fine; renaming is not.
3. **Don't use headless mode.** The whole point of CDP attach is to reuse the
   user's real, visible Chrome so login / 2FA / captcha are handled by a human.
4. **Be polite to ClickFunnels.** Keep the jittered delay in `src/sales.py`,
   stay single-threaded, and don't hammer pagination.

## Environment

- macOS or Linux. Python 3.10+ (tested on 3.12, 3.13).
- Dependencies: see `requirements.txt`. Install into `.venv/` (already
  gitignored).
- Chrome is launched via `./launch_chrome.sh`, which uses a **dedicated
  profile dir** (`~/.chrome-clickfunnels-profile`) so it doesn't collide with
  the user's personal Chrome.

## Runbook

```bash
# First time
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium      # fallback only

# Every session
./launch_chrome.sh                          # opens Chrome on :9222
# — log in to ClickFunnels in that window —
.venv/bin/python scrape.py --funnels        # step 1: enumerate -> funnels.json
.venv/bin/python scrape.py --sales          # step 2: scrape sales (resume-safe)

# Shortcuts
.venv/bin/python scrape.py --list-only      # enumerate + print, don't save
.venv/bin/python scrape.py --funnel <id>    # sales for a single funnel
.venv/bin/python scrape.py                  # = --funnels --sales
```

State lives in `output/_state.json`. To force a rescrape use `--no-resume` or
delete the file.

## Architecture in one glance

| File | Responsibility | Touch when… |
| --- | --- | --- |
| `scrape.py` | CLI, orchestration, resume logic | adding flags or top-level flow |
| `src/config.py` | env, URLs, field list | adding config knobs |
| `src/browser.py` | CDP attach + login fallback | CF login DOM changes |
| `src/funnels.py` | enumerate funnels from `/funnels` | funnel-list DOM changes |
| `src/sales.py` | per-funnel `stats/sales` scrape + pagination | sales-table DOM changes |
| `src/storage.py` | per-funnel CSV, combined CSV, state | changing output format |
| `debug_inspect.py` | dev-only DOM dumper | iterating on selectors |

Don't introduce new modules unless a concern doesn't fit any of the above.

## Iterating on selectors (the main loop you'll actually do)

The selectors are written defensively but CF ships DOM changes frequently.
When something returns 0 rows / 0 funnels:

1. Run `debug_inspect.py` — it attaches to the same Chrome, navigates to the
   target page, prints the active origin, lists funnel-like anchors, and saves
   the full HTML to `output/_debug_*.html`.
2. Inspect the saved HTML (or the live page in DevTools) and identify a stable
   selector — prefer `data-*` attributes or semantic ARIA roles over CSS
   classes, which CF changes often.
3. Update the relevant module (`funnels.py` or `sales.py`). Keep the fallback
   chain — each selector strategy uses a comma-separated list so multiple
   candidates are tried.
4. Re-run `--list-only` (for funnel enumeration) or `--limit 1` (for sales
   rows).

### Known quirks

- After login, CF redirects from `app.clickfunnels.com` to an **account
  subdomain** like `<workspace>-app.clickfunnels.com`. Code that hardcodes
  `app.clickfunnels.com` will silently do nothing. Read the active origin
  from `page.url` after the first authenticated request.
- Some accounts have "Classic" and "2.0" surfaces mixed. Paths with a `/k/`
  prefix are CF 2.0. If you find yourself on a `/k/...` URL when you expected
  Classic, the account may require a plan that exposes the Classic funnel
  editor.
- The sales table column headers can vary per funnel (some have coupon /
  refund columns). `_map_row` in `src/sales.py` matches by substring on
  header text — extend its `pick(...)` calls rather than hard-coding indices.
- The Classic sales view is `/funnels/<id>/contact_purchases`, and it
  **requires** the `?stats=alltime` query param. Without it the page
  defaults to a narrow recent-timeframe view and reports 0 rows even when
  the funnel has orders. Don't "simplify" the URL.

## Making changes

- Small, focused commits. One concern per commit. Don't bundle a selector fix
  with a refactor.
- Don't reformat files you didn't change.
- Don't add docstrings, comments, or type hints to code you didn't touch.
- If you add a new CLI flag, document it in `README.md`'s flag table.
- If you change `SALES_FIELDS`, update the README's column list too.

## Definition of done

A change is done when:

1. `./launch_chrome.sh && .venv/bin/python scrape.py --list-only` prints at
   least one funnel for an account that has funnels.
2. `.venv/bin/python scrape.py --limit 1` writes a non-empty
   `output/<funnel-id>.csv` with populated `order_id` / `date` / `amount`
   columns.
3. No credentials or `output/` artifacts are staged for commit.
