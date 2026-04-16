#!/usr/bin/env bash
# Launch Chrome/Chromium with remote debugging so the scraper can attach via CDP.
# Uses a dedicated profile dir so your main browser profile is untouched.
#
# Works on macOS and Linux. Honors these env vars:
#   CF_CHROME_PROFILE  profile dir (default: ~/.chrome-clickfunnels-profile)
#   CF_CHROME_PORT     debug port  (default: 9222)
#   CF_CHROME_BIN      override browser binary path

set -euo pipefail

PROFILE_DIR="${CF_CHROME_PROFILE:-$HOME/.chrome-clickfunnels-profile}"
PORT="${CF_CHROME_PORT:-9222}"

mkdir -p "$PROFILE_DIR"

FLAGS=(
  "--remote-debugging-port=$PORT"
  "--user-data-dir=$PROFILE_DIR"
  "--no-first-run"
  "--no-default-browser-check"
)

os="$(uname -s)"
case "$os" in
  Darwin)
    # macOS: prefer `open -na` so the app detaches cleanly
    APP="${CF_CHROME_BIN:-Google Chrome}"
    open -na "$APP" --args "${FLAGS[@]}"
    ;;
  Linux)
    # Linux: find a Chrome/Chromium binary, run detached
    if [[ -n "${CF_CHROME_BIN:-}" ]]; then
      BIN="$CF_CHROME_BIN"
    else
      for cand in google-chrome-stable google-chrome chromium chromium-browser; do
        if command -v "$cand" >/dev/null 2>&1; then
          BIN="$cand"
          break
        fi
      done
    fi
    if [[ -z "${BIN:-}" ]]; then
      echo "error: no Chrome/Chromium binary found." >&2
      echo "Install one (e.g. google-chrome-stable or chromium) or set CF_CHROME_BIN." >&2
      exit 1
    fi
    # Detach so the shell returns immediately
    nohup "$BIN" "${FLAGS[@]}" >/dev/null 2>&1 &
    disown || true
    ;;
  *)
    echo "error: unsupported OS '$os'. Run Chrome manually with:" >&2
    echo "  <chrome-binary> ${FLAGS[*]}" >&2
    exit 1
    ;;
esac

echo "Chrome launched on debug port $PORT"
echo "Profile dir: $PROFILE_DIR"
echo
echo "Next steps:"
echo "  1. In the Chrome window that just opened, log in to ClickFunnels."
echo "  2. Run:  .venv/bin/python scrape.py"
