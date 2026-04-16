from playwright.sync_api import sync_playwright, Page

from . import config


def attach():
    """Attach to a running Chrome via CDP. Returns (pw, browser, context, page)."""
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(config.CDP_URL)
    if not browser.contexts:
        raise RuntimeError(
            f"No browser context at {config.CDP_URL}. "
            "Run ./launch_chrome.sh first."
        )
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()
    return pw, browser, context, page


def ensure_logged_in(page: Page) -> None:
    page.goto(config.BASE_URL + "/", wait_until="domcontentloaded")
    if "sign_in" not in page.url:
        return

    if not config.USERNAME or not config.PASSWORD:
        raise RuntimeError("Not signed in and USERNAME/PASSWORD missing in .env")

    print("[auth] not signed in — submitting .env credentials")
    page.goto(config.LOGIN_URL, wait_until="domcontentloaded")
    page.fill('input[name="user[email]"]', config.USERNAME)
    page.fill('input[name="user[password]"]', config.PASSWORD)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("networkidle")
    if "sign_in" in page.url:
        raise RuntimeError("Login failed — check credentials, 2FA, or captcha")
    print("[auth] signed in")
