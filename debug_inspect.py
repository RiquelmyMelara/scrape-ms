"""Debug v2: use account subdomain, visit funnels listing, inspect DOM."""
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from src import config

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp(config.CDP_URL)
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    # Start from dashboard to let CF route to the account subdomain
    page.goto("https://app.clickfunnels.com/dashboard", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    origin = "{0.scheme}://{0.netloc}".format(urlparse(page.url))
    print("Account origin:", origin)
    print("Dashboard URL:", page.url)

    # Try multiple candidate funnel list paths
    candidates = ["/funnels", "/dashboard", "/k/funnels", "/funnels/list"]
    for path in candidates:
        url = origin + path
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception as e:
            print(f"\n[{path}] goto failed: {e}")
            continue
        print(f"\n[{path}] -> {page.url}")
        print("  title:", page.title())

        anchors = page.eval_on_selector_all(
            "a",
            "els => els.map(e => ({href: e.getAttribute('href'),"
            " text: (e.innerText || '').trim().slice(0, 60)}))",
        )
        # Only show funnel-looking hrefs
        fn_links = [a for a in anchors if a.get("href") and "/funnels/" in a["href"]]
        print(f"  funnel-like anchors: {len(fn_links)}")
        for a in fn_links[:15]:
            print(f"    {a['href']!r}  {a['text']!r}")

    # Save the /funnels page HTML for inspection
    from pathlib import Path
    out = Path("output/_debug_funnels.html")
    out.write_text(page.content(), encoding="utf-8")
    print(f"\nSaved last page HTML to {out}")
