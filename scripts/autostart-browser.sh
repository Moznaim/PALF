#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Launches Firefox ESR in Fullscreen Kiosk Mode while ensuring the On-Screen
# Virtual Keyboard (Squeekboard / wvkbd) layers OVER the browser surface.
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

# ── 2. Ensure Virtual Keyboard Daemon is running in Wayland / X11 ──────────────
# In modern Raspberry Pi OS (Bookworm), squeekboard or wvkbd handles virtual touch input.
# Launching squeekboard or wvkbd in the background ensures it is active on the overlay layer.
if command -v squeekboard &>/dev/null; then
  pgrep -x squeekboard >/dev/null || squeekboard &
elif command -v wvkbd-mobintl &>/dev/null; then
  pgrep -x wvkbd-mobintl >/dev/null || wvkbd-mobintl --layer overlay --hidden &
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
# MOZ_ENABLE_WAYLAND=1 ensures Firefox communicates directly via Wayland protocols,
# allowing the compositor to recognize the layer-shell protocols for virtual keyboards
# over the kiosk surface.

export MOZ_ENABLE_WAYLAND=1
exec "$BROWSER" --kiosk --private-window "$PALF_URL"
