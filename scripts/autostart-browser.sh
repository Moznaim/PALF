#!/usr/bin/env bash
# =============================================================================
# scripts/autostart-browser.sh
#
# Waits for the PALF-Vision Next.js server (localhost:3000) to be ready,
# then opens Chromium in kiosk mode pointing to the dashboard.
#
# This script is invoked by the LXDE autostart entry created by
# scripts/setup-autostart.sh — do NOT run it manually at login.
#
# Kiosk flags explained:
#   --kiosk              : fullscreen, no address bar, no close button
#   --noerrdialogs       : suppress crash dialogs on unclean shutdown
#   --disable-infobars   : hide "Chrome is being controlled" bar
#   --no-first-run       : skip the welcome/setup page
#   --disable-restore-session-state : don't restore previous tabs
#   --disable-session-crashed-bubble: suppress restore prompt
# =============================================================================

PALF_URL="http://localhost:3000"
MAX_WAIT=120     # seconds to wait for server before giving up
POLL_INTERVAL=2  # seconds between checks
BROWSER="chromium-browser"

# Fallback: some RPi OS versions name it just "chromium"
command -v "$BROWSER" &>/dev/null || BROWSER="chromium"

log() { echo "[palf-browser] $*"; }

log "Waiting for PALF-Vision server at $PALF_URL …"

elapsed=0
until curl -sf --max-time 2 "$PALF_URL" > /dev/null 2>&1; do
  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    log "Server did not respond after ${MAX_WAIT}s — opening browser anyway."
    break
  fi
  sleep "$POLL_INTERVAL"
  elapsed=$((elapsed + POLL_INTERVAL))
done

log "Server ready after ${elapsed}s. Launching $BROWSER …"

# Clean up any leftover Chromium lock files that prevent kiosk from starting
# after an unclean shutdown (power loss on RPi)
rm -f ~/.config/chromium/SingletonLock
rm -f ~/.config/chromium/SingletonSocket
rm -f ~/.config/chromium/Default/Preferences.bak

exec "$BROWSER" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --disable-restore-session-state \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --check-for-update-interval=31536000 \
  "$PALF_URL/dashboard"
