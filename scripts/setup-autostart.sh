#!/usr/bin/env bash
# =============================================================================
# scripts/setup-autostart.sh
#
# Configures the Raspberry Pi so that on every boot:
#   1. PM2 starts all PALF services (Next.js :3000 + FastAPI :4000 + Camera)
#   2. The desktop opens Chromium in kiosk mode at localhost:3000/dashboard
#
# Run once after initial setup:
#   chmod +x scripts/setup-autostart.sh
#   ./scripts/setup-autostart.sh
#
# Compatible with:
#   - Raspberry Pi OS Bookworm / Bullseye (64-bit) with LXDE desktop
#   - User: admin (or any desktop user — detects $USER automatically)
# =============================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="$REPO_DIR/scripts"
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; NC="\033[0m"

info()  { echo -e "${GREEN}[autostart] $*${NC}"; }
warn()  { echo -e "${YELLOW}[warn]      $*${NC}"; }
error() { echo -e "${RED}[error]     $*${NC}"; exit 1; }

CURRENT_USER="${SUDO_USER:-$USER}"
info "=== PALF-Vision Autostart Setup ==="
info "User: $CURRENT_USER"
info "Repo: $REPO_DIR"

# ── Sanity checks ─────────────────────────────────────────────────────────────
command -v pm2 &>/dev/null || error "PM2 not found. Run setup-raspi.sh first."

# Ensure Chromium or Firefox is installed (Chromium preferred for touch + virtual keyboard)
if ! command -v chromium-browser &>/dev/null && ! command -v chromium &>/dev/null && ! command -v firefox-esr &>/dev/null && ! command -v firefox &>/dev/null; then
  info "Installing Chromium browser (recommended for touchscreen & virtual keyboard support)..."
  sudo apt update && sudo apt install -y chromium-browser
fi

# ── Step 1: Make scripts executable ──────────────────────────────────────────
info "Making scripts executable…"
chmod +x "$SCRIPT_DIR/autostart-browser.sh"
chmod +x "$SCRIPT_DIR/setup-autostart.sh"

# ── Step 2: PM2 startup (systemd service — runs as current user) ──────────────
info "Registering PM2 with systemd so services survive reboots…"

# Generate the startup command and capture it
STARTUP_CMD=$(pm2 startup systemd -u "$CURRENT_USER" --hp "/home/$CURRENT_USER" 2>&1 \
  | grep "sudo env" || true)

if [ -n "$STARTUP_CMD" ]; then
  info "Running PM2 startup command…"
  eval "$STARTUP_CMD"
else
  info "PM2 startup already configured (or already run as root)."
fi

# Save current PM2 process list so it restores on reboot
info "Saving PM2 process list…"
pm2 save --force

# ── Step 3: Configure Autostart (Both Wayland and X11/LXDE compatible) ──────
info "Configuring Desktop Autostart for user: $CURRENT_USER…"

# Method A: XDG Autostart (.desktop file) — Works on Bookworm (Wayfire/Wayland) AND Bullseye (LXDE/X11)
XDG_AUTOSTART_DIR="/home/$CURRENT_USER/.config/autostart"
mkdir -p "$XDG_AUTOSTART_DIR"

cat <<EOF > "$XDG_AUTOSTART_DIR/palf-browser.desktop"
[Desktop Entry]
Type=Application
Name=PALF-Vision Web App
Comment=Start PALF-Vision AI with Touch & Virtual Keyboard support
Exec=bash $SCRIPT_DIR/autostart-browser.sh
Terminal=false
StartupNotify=false
EOF
chown -R "$CURRENT_USER:$CURRENT_USER" "$XDG_AUTOSTART_DIR"
info "Created XDG autostart entry: $XDG_AUTOSTART_DIR/palf-browser.desktop"

# Method B: Legacy LXDE-pi autostart (for Bullseye / Legacy X11)
AUTOSTART_DIR="/home/$CURRENT_USER/.config/lxsession/LXDE-pi"
AUTOSTART_FILE="$AUTOSTART_DIR/autostart"
mkdir -p "$AUTOSTART_DIR"
touch "$AUTOSTART_FILE"

SCREEN_OFF_ENTRY="@xset s off"
SCREEN_DPMS_ENTRY="@xset -dpms"
SCREEN_BLANK_ENTRY="@xset s noblank"

for entry in "$SCREEN_OFF_ENTRY" "$SCREEN_DPMS_ENTRY" "$SCREEN_BLANK_ENTRY"; do
  grep -qxF "$entry" "$AUTOSTART_FILE" || echo "$entry" >> "$AUTOSTART_FILE"
done

BROWSER_ENTRY="@bash $SCRIPT_DIR/autostart-browser.sh"
if grep -qF "autostart-browser.sh" "$AUTOSTART_FILE"; then
  sed -i "s|.*autostart-browser.sh.*|$BROWSER_ENTRY|" "$AUTOSTART_FILE"
else
  echo "$BROWSER_ENTRY" >> "$AUTOSTART_FILE"
fi
chown -R "$CURRENT_USER:$CURRENT_USER" "$AUTOSTART_DIR"
info "Configured legacy LXDE autostart file."

# ── Step 4: Configure Raspberry Pi to auto-login to desktop ──────────────────
info "Ensuring Raspberry Pi boots to desktop with auto-login…"

# raspi-config nonint: B4 = Desktop auto-login
if command -v raspi-config &>/dev/null; then
  sudo raspi-config nonint do_boot_behaviour B4
  info "Boot behaviour set to: Desktop with auto-login (B4)."
else
  warn "raspi-config not found. Manually set boot to 'Desktop Autologin' via:"
  warn "  sudo raspi-config → System Options → Boot / Auto Login → Desktop Autologin"
fi

# ── Step 5: Disable screen blanking system-wide (Pi config) ──────────────────
info "Disabling screen blanking in /etc/xdg/lxsession/LXDE-pi/autostart (system-wide)…"
SYSTEM_AUTOSTART="/etc/xdg/lxsession/LXDE-pi/autostart"
if [ -f "$SYSTEM_AUTOSTART" ]; then
  for entry in "@xset s off" "@xset -dpms" "@xset s noblank"; do
    sudo grep -qxF "$entry" "$SYSTEM_AUTOSTART" || echo "$entry" | sudo tee -a "$SYSTEM_AUTOSTART" > /dev/null
  done
fi

# Also set consoleblank=0 in cmdline.txt if not already set
CMDLINE="/boot/firmware/cmdline.txt"
[ -f "$CMDLINE" ] || CMDLINE="/boot/cmdline.txt"   # older Pi OS path
if [ -f "$CMDLINE" ] && ! grep -q "consoleblank=0" "$CMDLINE"; then
  sudo sed -i 's/$/ consoleblank=0/' "$CMDLINE"
  info "Set consoleblank=0 in $CMDLINE."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
info "=== Autostart setup complete! ==="
echo ""
echo -e "  What will happen on next boot:"
echo -e "    1. PM2 starts ${GREEN}palf-vision${NC} (Next.js :3000)"
echo -e "         + ${GREEN}palf-api${NC} (FastAPI :4000)"
echo -e "         + ${GREEN}palf-camera${NC} (camera service)"
echo -e "    2. Desktop auto-logs in as ${GREEN}$CURRENT_USER${NC}"
echo -e "    3. Browser opens in ${GREEN}touch app mode${NC} → ${GREEN}http://localhost:3000/dashboard${NC}"
echo -e "       (Virtual on-screen keyboard enabled and ready)"
echo -e "    4. Screen stays ${GREEN}on (no blanking)${NC}"
echo ""
echo -e "  To test without rebooting:"
echo -e "    ${GREEN}bash $SCRIPT_DIR/autostart-browser.sh${NC}"
echo ""
echo -e "  To exit kiosk mode on the Pi:"
echo -e "    Press ${YELLOW}Alt+F4${NC} (closes browser) or ${YELLOW}Ctrl+Alt+T${NC} (opens terminal)"
echo ""
warn "Reboot now to apply all changes:"
warn "  sudo reboot"
echo ""
