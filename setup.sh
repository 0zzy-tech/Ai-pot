#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AI Honeypot — Raspberry Pi / Ubuntu setup script
#
# Usage:
#   chmod +x setup.sh
#   sudo ./setup.sh
#
# What it does:
#   1. Installs system dependencies
#   2. Creates a Python virtualenv
#   3. Installs Python packages
#   4. Installs and enables the systemd service
#   5. Opens the firewall port (if ufw is active)
#
# After running, edit config.py to change ADMIN_PASSWORD before starting.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

INSTALL_DIR="/home/pi/ai-honeypot"
SERVICE_FILE="ai-honeypot.service"
SERVICE_NAME="ai-honeypot"
PYTHON_BIN="python3"

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Root check ─────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Please run as root: sudo $0"

# ── Detect actual user (for service ownership) ─────────────────────────────────
if [[ -n "${SUDO_USER:-}" ]]; then
  REAL_USER="$SUDO_USER"
else
  REAL_USER="pi"
  warn "SUDO_USER not set; defaulting service user to 'pi'. Edit ai-honeypot.service if needed."
fi

info "Installing for user: $REAL_USER"
INSTALL_DIR="/home/${REAL_USER}/ai-honeypot"

# ── 1. System packages ─────────────────────────────────────────────────────────
info "Installing system packages…"
apt-get update -qq
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip \
  2>/dev/null

# ── 2. Copy project files ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info "Copying project to ${INSTALL_DIR}…"
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
chown -R "${REAL_USER}:${REAL_USER}" "$INSTALL_DIR"

# ── 3. Python virtualenv ───────────────────────────────────────────────────────
info "Creating Python virtualenv…"
sudo -u "$REAL_USER" "$PYTHON_BIN" -m venv "${INSTALL_DIR}/venv"

info "Installing Python dependencies…"
sudo -u "$REAL_USER" "${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$REAL_USER" "${INSTALL_DIR}/venv/bin/pip" install --quiet \
  -r "${INSTALL_DIR}/requirements.txt"

# ── 4. Systemd service ─────────────────────────────────────────────────────────
info "Installing systemd service…"

# Patch service file to use actual user
SERVICE_SRC="${INSTALL_DIR}/${SERVICE_FILE}"
sed -i "s/^User=pi$/User=${REAL_USER}/"   "$SERVICE_SRC"
sed -i "s/^Group=pi$/Group=${REAL_USER}/" "$SERVICE_SRC"
sed -i "s|/home/pi/|/home/${REAL_USER}/|g" "$SERVICE_SRC"

cp "$SERVICE_SRC" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"

# ── 5. Firewall ────────────────────────────────────────────────────────────────
if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
  info "Opening UFW port 11434/tcp…"
  ufw allow 11434/tcp comment "AI Honeypot (Ollama)"
else
  warn "UFW not active — you may need to open port 11434 manually."
fi

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN} AI Honeypot installed successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Install dir : ${INSTALL_DIR}"
echo "  Config file : ${INSTALL_DIR}/config.py"
echo ""
echo -e "${YELLOW}  IMPORTANT: Change ADMIN_PASSWORD in config.py before starting!${NC}"
echo ""
echo "  Start service  : sudo systemctl start ${SERVICE_NAME}"
echo "  View logs      : sudo journalctl -u ${SERVICE_NAME} -f"
echo "  Dashboard      : http://<pi-ip>:11434/__admin"
echo "                   (default login: admin / changeme)"
echo ""
