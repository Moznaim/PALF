#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Launches Firefox ESR in Fullscreen Kiosk Mode while ensuring whichever
# on-screen keyboard is installed (Squeekboard, Matchbox, or Onboard)
# is active and layers OVER the browser surface.
# =============================================================================

PALF_URL="http://localhost:3000/login"
MAX_WAIT=120     # seconds to wait for server before giving up
POLL_INTERVAL=2  # seconds between checks

log() { echo "[palf-browser] $*"; }

# ── 1. Target Firefox ESR ─────────────────────────────────────────────────────
if command -v firefox-esr &>/dev/null; then
  BROWSER="firefox-esr"
elif command -v firefox &>/dev/null; then
  BROWSER="firefox"
else
  log "Firefox not found! Installing firefox-esr..."
  sudo apt update && sudo apt install -y firefox-esr
  BROWSER="firefox-esr"
fi

# ── 2. Detect & Launch whichever Virtual Keyboard is present ──────────────────
# - Squeekboard : Default on Raspberry Pi OS Bookworm (Wayland)
# - Onboard     : Popular feature-rich OSK
# - Matchbox    : Classic lightweight RPi keyboard (Bullseye / X11)
if command -v squeekboard &>/dev/null; then
  pgrep -x squeekboard >/dev/null || squeekboard &
  log "Active on-screen keyboard: Squeekboard"
elif command -v onboard &>/dev/null; then
  pgrep -x onboard >/dev/null || onboard &
  log "Active on-screen keyboard: Onboard"
elif command -v matchbox-keyboard &>/dev/null; then
  pgrep -x matchbox-keyboard >/dev/null || matchbox-keyboard &
  log "Active on-screen keyboard: Matchbox"
fi

log "Waiting for PALF-Vision server at http://localhost:3000 …"

# ── 3. Wait until localhost:3000 responds ──────────────────────────────────────
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

# ── 4. Launch Firefox ESR in Kiosk with Wayland Layer Support ──────────────────
export MOZ_ENABLE_WAYLAND=1
exec "$BROWSER" --kiosk --private-window "$PALF_URL"
