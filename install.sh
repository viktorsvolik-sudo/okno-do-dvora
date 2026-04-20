#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# Okno do dvora — install.sh
# Raspberry Pi 4B · Debian 13
#
# Použití:
#   chmod +x install.sh
#   ./install.sh
# ─────────────────────────────────────────────────────────────────

set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(whoami)"
SERVICE_NAME="okno-do-dvora"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║      Okno do dvora — instalace       ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "→ Složka: $APP_DIR"
echo "→ Uživatel: $USER_NAME"
echo ""

# ── 1. SYSTÉMOVÉ BALÍČKY ────────────────────────────────────────
echo "[1/4] Instaluji systémové balíčky..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-pygame \
    python3-requests \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-ttf-dev \
    fonts-dejavu-core \
    --no-install-recommends

echo "      ✓ Hotovo"

# ── 2. PYTHON KNIHOVNY ───────────────────────────────────────────
echo "[2/4] Instaluji Python knihovny..."
pip3 install --break-system-packages --quiet pygame requests 2>/dev/null || true
echo "      ✓ Hotovo"

# ── 3. TEST SPUŠTĚNÍ ─────────────────────────────────────────────
echo "[3/4] Testuji import modulů..."
python3 -c "import pygame; import requests; print('      ✓ pygame', pygame.version.ver, '· requests OK')"

# ── 4. SYSTEMD AUTOSTART ─────────────────────────────────────────
echo "[4/4] Nastavuji autostart (systemd)..."

# Zjisti cestu k pythonu
PYTHON_BIN="$(which python3)"

# Zjisti displej (fallback na :0)
DISPLAY_VAR="${DISPLAY:-:0}"

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Okno do dvora - Weather Display
After=network-online.target graphical.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
Environment=DISPLAY=${DISPLAY_VAR}
Environment=SDL_VIDEODRIVER=x11
Environment=PYTHONUNBUFFERED=1
ExecStart=${PYTHON_BIN} ${APP_DIR}/weather.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service

echo "      ✓ Hotovo"
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Instalace dokončena!                                    ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Spustit hned:     sudo systemctl start okno-do-dvora   ║"
echo "║  Zastavit:         sudo systemctl stop okno-do-dvora    ║"
echo "║  Logy:             journalctl -u okno-do-dvora -f       ║"
echo "║  Otestovat ručně:  python3 weather.py                   ║"
echo "║                                                          ║"
echo "║  Po restartu RPi se spustí automaticky.                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Nabídni okamžité spuštění
read -p "Spustit aplikaci hned? [Y/n] " answer
case "$answer" in
    [nN]*) echo "OK, spustí se po restartu." ;;
    *)
        echo "Spouštím..."
        sudo systemctl start ${SERVICE_NAME}.service
        echo "Běží! Stav:"
        sudo systemctl status ${SERVICE_NAME}.service --no-pager -l
        ;;
esac
