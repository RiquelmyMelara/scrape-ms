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

3. **Sanity check** — list detected funnels without scraping:

   ```bash
   .venv/bin/python scrape.py --list-only
   ```

4. **Smoke test** one funnel end-to-end:

   ```bash
   .venv/bin/python scrape.py --limit 1
   ```

5. **Full run** (resume-safe; completed funnel IDs are tracked in
   `output/_state.json`):

   ```bash
   .venv/bin/python scrape.py
   ```

## CLI flags

| Flag | Purpose |
| --- | --- |
| `--funnel <id>` | Scrape only one funnel by ID |
| `--limit <n>` | Cap number of funnels (testing) |
| `--list-only` | Enumerate funnels and exit |
| `--no-resume` | Ignore `_state.json` and rescrape everything |

## Output

```
output/
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

- **`No browser context at http://localhost:9222`** — Chrome isn't running
  with the debug port. Re-run `./launch_chrome.sh`.
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
