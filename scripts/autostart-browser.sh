#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Waits for the PALF-Vision Next.js server (localhost:3000) to be ready,
# then opens Firefox (or Chromium as fallback) in kiosk mode pointing to the dashboard.
#
# Kiosk flags for Firefox:
#   --kiosk <URL>      : Opens in fullscreen kiosk mode without browser chrome
#   --private-window   : Prevents caching session crash/restore dialogs
# =============================================================================

PALF_URL="http://localhost:3000/dashboard"
MAX_WAIT=120     # seconds to wait for server before giving up
POLL_INTERVAL=2  # seconds between checks

log() { echo "[palf-browser] $*"; }

# ── 1. Detect browser (Firefox preferred, Chromium fallback) ──────────────────
if command -v firefox-esr &>/dev/null; then
  BROWSER="firefox-esr"
elif command -v firefox &>/dev/null; then
  BROWSER="firefox"
elif command -v chromium-browser &>/dev/null; then
  BROWSER="chromium-browser"
elif command -v chromium &>/dev/null; then
  BROWSER="chromium"
else
  log "Neither Firefox nor Chromium found! Please install firefox-esr:"
  log "  sudo apt install -y firefox-esr"
  exit 1
fi

log "Detected browser: $BROWSER"
log "Waiting for PALF-Vision server at http://localhost:3000 …"

# ── 2. Wait until localhost:3000 responds ──────────────────────────────────────
elapsed=0
until curl -sf --max-time 2 "http://localhost:3000" > /dev/null 2>&1; do
  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    log "Server did not respond after ${MAX_WAIT}s — launching browser anyway."
    break
  fi
  sleep "$POLL_INTERVAL"
  elapsed=$((elapsed + POLL_INTERVAL))
done

log "Server ready after ${elapsed}s. Launching $BROWSER …"

# ── 3. Launch browser in kiosk mode ───────────────────────────────────────────
if [[ "$BROWSER" == *"firefox"* ]]; then
  # Firefox kiosk launch
  # --kiosk : full screen kiosk without URL bar or window borders
  # --private-window : avoids "Restore Session" alerts after abrupt power-cuts
  exec "$BROWSER" --kiosk --private-window "$PALF_URL"
else
  # Chromium fallback
  rm -f ~/.config/chromium/SingletonLock ~/.config/chromium/SingletonSocket
  exec "$BROWSER" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-restore-session-state \
    --disable-session-crashed-bubble \
    "$PALF_URL"
fi
