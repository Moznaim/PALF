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

# ── 4. Python + picamera2 + virtualenv ───────────────────────────────────────
info "Installing picamera2 and python dependencies…"
sudo apt install -y python3-picamera2 python3-pip python3-venv

# ── 5. Enable RPi camera (V4L2 via raspi-config) ─────────────────────────────
info "Enabling camera interface…"
sudo raspi-config nonint do_camera 0

# ── 6. Serialport dependencies (for ESP32 USB serial) ────────────────────────
info "Installing serialport build dependencies…"
sudo apt install -y build-essential libudev-dev

# ── 7. Frontend dependencies ─────────────────────────────────────────────────
info "Installing Node.js frontend dependencies…"
cd "$REPO_DIR"
npm install

# ── 8. Backend Python virtual environment & dependencies ─────────────────────
info "Setting up Python virtual environment for FastAPI backend…"
if [ ! -d "$REPO_DIR/backend/venv" ]; then
  python3 -m venv --system-site-packages "$REPO_DIR/backend/venv"
fi

info "Installing PyTorch & backend requirements inside venv…"
"$REPO_DIR/backend/venv/bin/pip" install --upgrade pip
"$REPO_DIR/backend/venv/bin/pip" install -r "$REPO_DIR/backend/requirements.txt"

# ── 9. Environment file ──────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/.env.local" ]; then
  info "Creating .env.local from template…"
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env.local"
  # Set RPi-appropriate defaults
  sed -i 's/NEXT_PUBLIC_CAMERA_MODE=WEBCAM/NEXT_PUBLIC_CAMERA_MODE=PICAMERA/' "$REPO_DIR/.env.local" || true
  sed -i 's/NEXT_PUBLIC_MODEL_MODE=MOCK/NEXT_PUBLIC_MODEL_MODE=PYTORCH/' "$REPO_DIR/.env.local" || true
  warn "Configured .env.local for RPi (PICAMERA + PYTORCH)."
else
  info ".env.local already exists — keeping existing settings."
fi

# ── 10. Check for model checkpoint ───────────────────────────────────────────
EFF_CKPT="$REPO_DIR/backend/models/efficientnet_b0_attention_best.pt"
RES_CKPT="$REPO_DIR/backend/models/resnet50_concat_best.pt"
if [ ! -f "$EFF_CKPT" ] && [ ! -f "$RES_CKPT" ]; then
  warn "No model checkpoint found in backend/models/."
  warn "Please copy 'efficientnet_b0_attention_best.pt' or 'resnet50_concat_best.pt' to backend/models/."
else
  [ -f "$EFF_CKPT" ] && info "Found EfficientNet checkpoint: $EFF_CKPT"
  [ -f "$RES_CKPT" ] && info "Found ResNet-50 checkpoint: $RES_CKPT"
fi

# ── 11. Build Next.js ────────────────────────────────────────────────────────
info "Building Next.js for production…"
npm run build

# ── 12. Create logs directory ────────────────────────────────────────────────
mkdir -p "$REPO_DIR/logs"

# ── 13. Start with PM2 ───────────────────────────────────────────────────────
info "Starting all services with PM2 (Next.js, Camera service, Backend API)…"
pm2 start "$REPO_DIR/ecosystem.config.js"
pm2 save

# ── 14. PM2 startup (auto-start on boot) ─────────────────────────────────────
info "Configuring PM2 to start on boot…"
warn "Run the command printed by PM2 below if not already done (sudo env PATH=...)"
pm2 startup || true

echo ""
info "=== Setup complete! ==="
echo -e "  Frontend UI:   ${GREEN}http://$(hostname -I | awk '{print $1}'):3000${NC}"
echo -e "  Backend API:   ${GREEN}http://$(hostname -I | awk '{print $1}'):4000/docs${NC}"
echo -e "  View logs:     ${GREEN}pm2 logs${NC}"
echo -e "  Process list:  ${GREEN}pm2 status${NC}"
echo ""
