#!/bin/bash
# ============================================================
#  HN Imóveis ERP — Atualizar HTML em produção
#  Uso: sudo bash atualizar.sh
# ============================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

APP_DIR="/var/www/imv-erp"
HTML_FILE="$(dirname "$0")/../mockup_erp_imobiliario.html"

[ "$EUID" -ne 0 ] && echo "Execute com sudo: sudo bash atualizar.sh" && exit 1

echo -e "${BLUE}[..] Copiando HTML atualizado...${NC}"
cp "$HTML_FILE" "$APP_DIR/index.html"
chown www-data:www-data "$APP_DIR/index.html"
chmod 644 "$APP_DIR/index.html"

echo -e "${GREEN}[OK] Sistema atualizado!${NC}"
echo -e "     Acesse: http://$(hostname -I | awk '{print $1}')"
