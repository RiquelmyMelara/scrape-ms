# scrape-ms

Scrape sales data from **ClickFunnels Classic** by attaching Playwright to a
real Chrome session over CDP, so your login (including 2FA/captcha) stays
in-browser.

For each funnel the scraper visits `Stats → Sales`, paginates through every
page, and writes rows to CSV.

## Stack

- Python 3.10+
- [Playwright](https://playwright.dev/python/) (attaches to Chrome via CDP)
- `python-dotenv` for credentials

## One-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium   # used only as a fallback
cp .env.example .env                    # then fill in real credentials
```

## Running

1. **Launch Chrome with remote debugging** (uses a dedicated profile so your
   personal Chrome is untouched):

   ```bash
   ./launch_chrome.sh
   ```

2. **Log in to ClickFunnels** in the Chrome window that just opened. The
   scraper also has an `.env`-based login fallback, but doing it manually is
   safer when 2FA / captcha is in play.

3. **Step 1 — enumerate funnels** (saves to `output/funnels.json`):

   ```bash
   .venv/bin/python scrape.py --funnels
   ```

4. **Step 2 — scrape sales** for every funnel in that list:

   ```bash
   .venv/bin/python scrape.py --sales
   ```

   Or do both in one run: `.venv/bin/python scrape.py --funnels --sales`
   (this is also what you get with no flags).

5. **Smoke test** a single funnel without enumerating:

   ```bash
   .venv/bin/python scrape.py --funnel 13500377
   ```

   The sales step is **resume-safe**: completed funnel IDs are tracked in
   `output/_state.json`. Rerun `--sales` to pick up where it left off.

## CLI flags

| Flag | Purpose |
| --- | --- |
| `--funnels` | Enumerate funnels and save `output/funnels.json` |
| `--sales` | Scrape sales for each funnel in the saved list |
| `--enrich` | Visit contact profiles to fill in `purchase_timestamp` on each sales row |
| `--upload` | Push all per-funnel CSVs to PostgreSQL (needs `DB_*` vars in `.env`) |
| `--funnel <id>` | Operate on a single funnel id (combines with other step flags) |
| `--limit <n>` | Cap number of funnels (testing) |
| `--list-only` | Enumerate and print funnels; don't save or scrape |
| `--no-resume` | Ignore `_state.json` and rescrape/re-enrich everything |

Running with no flags is equivalent to `--funnels --sales`. `--enrich` and
`--upload` are opt-in. `--upload` does not require Chrome — it reads
the CSVs and pushes to the database.

## Output

```
output/
├── funnels.json         enumerated funnels (input to --sales)
├── <funnel-id>.csv      one file per funnel
├── sales_all.csv        combined file, regenerated at end of each run
└── _state.json          which funnel IDs are already done
```

Columns: `order_id, date, customer_name, email, product, amount, currency,
status, funnel_id, funnel_name`.

## Project layout

```
scrape-ms/
├── launch_chrome.sh       launches Chrome on port 9222 w/ dedicated profile
├── scrape.py              CLI entrypoint
├── src/
│   ├── config.py          env vars, URLs, output paths, field list
│   ├── browser.py         CDP attach + login fallback
│   ├── funnels.py         enumerate funnels (paginated)
│   ├── sales.py           per-funnel sales scrape (paginated)
│   └── storage.py         CSV + resume state
├── debug_inspect.py       dev-only: dumps DOM to help refine selectors
├── requirements.txt
├── .env.example
└── output/                generated (gitignored)
```

## Troubleshooting

- **`No browser context at http://localhost:9222`** / **`ECONNREFUSED ... :9222`**
  — Chrome isn't running with the debug port. Re-run `./launch_chrome.sh`.
  On Linux, make sure a Chrome/Chromium binary is installed
  (`google-chrome-stable`, `google-chrome`, `chromium`, or `chromium-browser`),
  or set `CF_CHROME_BIN=/path/to/chrome`.
- **Login failed** — 2FA/captcha likely. Log in manually in the Chrome window,
  then rerun.
- **`funnels total: 0`** — the DOM selectors in `src/funnels.py` don't match
  your account. Use `debug_inspect.py` to dump the real DOM and adjust
  selectors. See `AGENTS.md` for the iteration workflow.
- **CSV has empty columns** — the sales-table headers differ from what
  `src/sales.py::_map_row` expects. Add matching keys to the `pick(...)` calls.

## Security

`.env` is gitignored. Do not commit credentials. Rotate the ClickFunnels
password if you ever paste it into a shared location.
