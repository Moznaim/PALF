#!/usr/bin/env bash
# =============================================================================
# scripts/deploy.sh
#
# Run this on the Raspberry Pi whenever new code is pushed to GitHub.
# It pulls the latest code, reinstalls dependencies if needed,
# rebuilds Next.js, and restarts the PM2 process.
#
# Usage (from the project directory on the RPi):
#   bash scripts/deploy.sh
#
# Or from anywhere:
#   bash ~/palf-vision/scripts/deploy.sh
# =============================================================================

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="palf-vision"
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
info "Installing dependencies…"
npm install

# ── 3. Rebuild Next.js ───────────────────────────────────────────────────────
info "Building production bundle…"
npm run build

# ── 4. Restart (or start) PM2 process ────────────────────────────────────────
if pm2 list | grep -q "$APP_NAME"; then
  info "Restarting PM2 process '$APP_NAME'…"
  pm2 restart "$APP_NAME"
else
  warn "PM2 process '$APP_NAME' not found — starting fresh…"
  pm2 start ecosystem.config.js
fi

pm2 save

echo ""
info "=== Deploy complete! ==="
echo -e "  App URL:   ${GREEN}http://$(hostname -I | awk '{print $1}'):3000${NC}"
echo -e "  PM2 logs:  ${GREEN}pm2 logs $APP_NAME${NC}"
echo ""
