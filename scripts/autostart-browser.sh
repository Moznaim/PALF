#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Waits for the PALF-Vision Next.js server (localhost:3000) to be ready,
# then opens the browser in app / kiosk mode while keeping on-screen keyboards
# (Squeekboard / Matchbox / Onboard / Wayfire OSK) functioning properly.
# =============================================================================

PALF_URL="http://localhost:3000/dashboard"
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

log "Server ready after ${elapsed}s. Launching $BROWSER …"

# ── 3. Launch browser ──────────────────────────────────────────────────────────
# NOTE on On-Screen Keyboard & Fullscreen:
# In pure --kiosk mode, the window manager gives exclusive z-index to the browser,
# hiding on-screen keyboards (Squeekboard, Matchbox, Onboard) behind the window.
# We use --app mode with touch-events and touch-screen-optimized flags so the OSK
# can float over the text input fields.

if [[ "$BROWSER" == *"chromium"* ]]; then
  rm -f ~/.config/chromium/SingletonLock ~/.config/chromium/SingletonSocket
  exec "$BROWSER" \
    --app="$PALF_URL" \
    --start-maximized \
    --touch-events=enabled \
    --enable-virtual-keyboard \
    --noerrdialogs \
    --disable-infobars \
    --no-first-run \
    --disable-session-crashed-bubble
else
  # Firefox: Launch without exclusive --kiosk lock so OSK layer can pop up
  exec "$BROWSER" --private-window --start-maximized "$PALF_URL"
fi
