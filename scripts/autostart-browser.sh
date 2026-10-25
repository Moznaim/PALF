#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Waits for the PALF-Vision Next.js server (localhost:3000) to be ready,
# then opens the browser in true borderless fullscreen pointing to the LOGIN page
# (http://localhost:3000/login), while ensuring the on-screen keyboard functions.
# =============================================================================

PALF_URL="http://localhost:3000/login"
MAX_WAIT=120     # seconds to wait for server before giving up
POLL_INTERVAL=2  # seconds between checks

log() { echo "[palf-browser] $*"; }

# ── 1. Detect browser (Chromium is best for Raspberry Pi on-screen touch keyboard) ─
if command -v chromium-browser &>/dev/null; then
  BROWSER="chromium-browser"
elif command -v chromium &>/dev/null; then
  BROWSER="chromium"
elif command -v firefox-esr &>/dev/null; then
  BROWSER="firefox-esr"
elif command -v firefox &>/dev/null; then
  BROWSER="firefox"
else
  log "Neither Chromium nor Firefox found!"
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

log "Server ready after ${elapsed}s. Launching $BROWSER on $PALF_URL …"

# ── 3. Launch browser in full-screen touch mode ────────────────────────────────
# --start-fullscreen + --app gives true 100% kiosk fullscreen with NO title bar,
# NO address bar, and NO window borders, but keeps the window manager layer open
# so the on-screen keyboard can pop up over text inputs!

if [[ "$BROWSER" == *"chromium"* ]]; then
  rm -f ~/.config/chromium/SingletonLock ~/.config/chromium/SingletonSocket
  exec "$BROWSER" \
    --app="$PALF_URL" \
    --start-fullscreen \
    --touch-events=enabled \
    --enable-virtual-keyboard \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble
else
  # Firefox: Launch fullscreen to /login
  exec "$BROWSER" --private-window --kiosk "$PALF_URL"
fi
