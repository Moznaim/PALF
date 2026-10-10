#!/usr/bin/env bash
# =============================================================================
# scripts/deploy.sh
#
# Run this on the Raspberry Pi whenever new code is pushed to GitHub.
# It pulls the latest code, reinstalls dependencies if needed,
# rebuilds Next.js, and restarts all PM2 processes (web + camera service).
#
# Usage (from the project directory on the RPi):
#   bash scripts/deploy.sh
# =============================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN="\033[0;32m"; YELLOW="\033[1;33m"; NC="\033[0m"

info() { echo -e "${GREEN}[deploy] $*${NC}"; }
warn() { echo -e "${YELLOW}[warn]   $*${NC}"; }

info "=== PALF-Vision AI — Deploy ==="
info "Directory: $REPO_DIR"
cd "$REPO_DIR"

# ── 1. Pull latest code ───────────────────────────────────────────────────────
info "Pulling latest code from GitHub…"
git pull

# ── 2. Install / update dependencies ─────────────────────────────────────────
info "Installing Node.js dependencies…"
npm install

if [ -d "$REPO_DIR/backend/venv" ]; then
  info "Updating Python backend dependencies…"
  "$REPO_DIR/backend/venv/bin/pip" install -r "$REPO_DIR/backend/requirements.txt"
fi

# ── 3. Rebuild Next.js ───────────────────────────────────────────────────────
info "Building production bundle…"
npm run build

# ── 4. Restart or start PM2 processes ────────────────────────────────────────
info "Updating PM2 processes from ecosystem.config.js…"
pm2 delete all 2>/dev/null || true
pm2 start ecosystem.config.js
pm2 save

echo ""
info "=== Deploy complete! ==="
echo -e "  App URL:    ${GREEN}http://$(hostname -I | awk '{print $1}'):3000${NC}"
echo -e "  PM2 status: ${GREEN}pm2 status${NC}"
echo -e "  PM2 logs:   ${GREEN}pm2 logs${NC}"
echo ""
