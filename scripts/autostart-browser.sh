#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Waits for the PALF-Vision Next.js server (localhost:3000) to be ready,
# then opens FIREFOX-ESR in fullscreen mode pointing to the LOGIN page
# (http://localhost:3000/login).
# =============================================================================

PALF_URL="http://localhost:3000/login"
MAX_WAIT=120     # seconds to wait for server before giving up
POLL_INTERVAL=2  # seconds between checks

log() { echo "[palf-browser] $*"; }

# ── 1. Target Firefox ESR explicitly ──────────────────────────────────────────
if command -v firefox-esr &>/dev/null; then
  BROWSER="firefox-esr"
elif command -v firefox &>/dev/null; then
  BROWSER="firefox"
else
  log "Firefox not found! Installing firefox-esr..."
  sudo apt update && sudo apt install -y firefox-esr
  BROWSER="firefox-esr"
fi

log "Using browser: $BROWSER"
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

# ── 3. Launch Firefox ESR ─────────────────────────────────────────────────────
# --kiosk : True borderless fullscreen covering 100% of display
# --private-window : Prevents session restore / crash prompt on power loss
exec "$BROWSER" --kiosk --private-window "$PALF_URL"
