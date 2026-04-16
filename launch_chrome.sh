#!/usr/bin/env bash
# Launch Chrome with remote debugging so the scraper can attach via CDP.
# Uses a dedicated profile dir so your main Chrome profile is untouched.

set -euo pipefail

PROFILE_DIR="${CF_CHROME_PROFILE:-$HOME/.chrome-clickfunnels-profile}"
PORT="${CF_CHROME_PORT:-9222}"

mkdir -p "$PROFILE_DIR"

open -na "Google Chrome" --args \
  --remote-debugging-port="$PORT" \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check

echo "Chrome launched on debug port $PORT"
echo "Profile dir: $PROFILE_DIR"
echo
echo "Next steps:"
echo "  1. In the Chrome window that just opened, log in to ClickFunnels."
echo "  2. Run:  python scrape.py"
