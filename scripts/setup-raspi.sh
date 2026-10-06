#!/usr/bin/env bash
# =============================================================================
# scripts/setup-raspi.sh
#
# One-shot setup for PALF-Vision AI on a fresh Raspberry Pi OS (Bookworm 64-bit)
#
# Usage:
#   chmod +x scripts/setup-raspi.sh
#   ./scripts/setup-raspi.sh
#
# Or directly after cloning:
#   bash scripts/setup-raspi.sh
# =============================================================================

set -e  # exit immediately on any error

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"

info()  { echo -e "${GREEN}[setup] $*${NC}"; }
warn()  { echo -e "${YELLOW}[warn]  $*${NC}"; }

info "=== PALF-Vision AI — Raspberry Pi Setup ==="
info "Project directory: $REPO_DIR"

# ── 1. System update ─────────────────────────────────────────────────────────
info "Updating system packages…"
sudo apt update && sudo apt upgrade -y

# ── 2. Node.js 20 LTS ────────────────────────────────────────────────────────
if command -v node &>/dev/null; then
  info "Node.js already installed: $(node -v)"
else
  info "Installing Node.js 20 LTS…"
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt install -y nodejs
  info "Node.js installed: $(node -v)"
fi

# ── 3. PM2 (process manager) ─────────────────────────────────────────────────
if command -v pm2 &>/dev/null; then
  info "PM2 already installed: $(pm2 -v)"
else
  info "Installing PM2…"
  sudo npm install -g pm2
fi

# ── 4. Python + picamera2 (for camera backend when ready) ────────────────────
info "Installing picamera2 and python dependencies…"
sudo apt install -y python3-picamera2 python3-pip

# ── 5. Enable RPi camera (V4L2 via raspi-config) ─────────────────────────────
info "Enabling camera interface…"
sudo raspi-config nonint do_camera 0
# This allows the camera to appear as /dev/video0 (getUserMedia compatible)

# ── 6. Serialport dependencies (for ESP32 USB serial later) ──────────────────
info "Installing serialport build dependencies…"
sudo apt install -y build-essential libudev-dev

# ── 7. npm install ───────────────────────────────────────────────────────────
info "Installing Node.js dependencies…"
cd "$REPO_DIR"
npm install

# ── 8. Environment file ──────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/.env.local" ]; then
  info "Creating .env.local from template…"
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env.local"
  warn "Edit .env.local to set CAMERA_MODE, DEVICE_MODE, etc. for your hardware."
  warn "  nano $REPO_DIR/.env.local"
else
  info ".env.local already exists — skipping."
fi

# ── 9. Build Next.js ─────────────────────────────────────────────────────────
info "Building Next.js for production…"
npm run build

# ── 10. Create logs directory ────────────────────────────────────────────────
mkdir -p "$REPO_DIR/logs"

# ── 11. Start with PM2 ───────────────────────────────────────────────────────
info "Starting app with PM2…"
pm2 start "$REPO_DIR/ecosystem.config.js"
pm2 save

# ── 12. PM2 startup (auto-start on boot) ─────────────────────────────────────
info "Configuring PM2 to start on boot…"
warn "Run the command that PM2 prints below (it starts with 'sudo env PATH=...')"
pm2 startup

echo ""
info "=== Setup complete! ==="
echo -e "  App running at: ${GREEN}http://$(hostname -I | awk '{print $1}'):3000${NC}"
echo -e "  View logs:      ${GREEN}pm2 logs palf-vision${NC}"
echo -e "  Update app:     ${GREEN}bash $REPO_DIR/scripts/deploy.sh${NC}"
echo ""
