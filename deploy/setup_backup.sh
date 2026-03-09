#!/bin/bash
# ============================================================
#  HN Imóveis ERP — Setup de Backup Automático
#  Configura: rclone + Google Drive + cron diário às 2h da manhã
#  Uso: sudo bash setup_backup.sh
# ============================================================

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[..] $1${NC}"; }
warn() { echo -e "${YELLOW}[AVISO]${NC} $1"; }
err()  { echo -e "${RED}[ERRO] $1${NC}"; exit 1; }

[ "$EUID" -ne 0 ] && err "Execute com sudo: sudo bash setup_backup.sh"

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_SCRIPT="${DEPLOY_DIR}/backup.sh"
CRON_USER="root"

echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${BOLD}   HN Imóveis ERP — Setup de Backup            ${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""

# ── instala rclone ─────────────────────────────────────────────
if command -v rclone &>/dev/null; then
  log "rclone já instalado: $(rclone version | head -1)"
else
  info "Instalando rclone..."
  curl -fsSL https://rclone.org/install.sh | bash
  log "rclone instalado"
fi

# ── configura Google Drive ─────────────────────────────────────
echo ""
echo -e "${BOLD}── Configuração do Google Drive ────────────────────${NC}"
echo ""
echo "  Agora vamos conectar o rclone ao seu Google Drive."
echo "  O rclone vai abrir um link de autorização no navegador."
echo ""
echo -e "${YELLOW}  IMPORTANTE: Execute este passo no computador com interface gráfica,"
echo -e "  ou use a flag --no-browser e autorize pelo celular/outro PC.${NC}"
echo ""

read -rp "  Pressione ENTER para iniciar a configuração do Google Drive..."

# Roda como o usuário root (backup vai rodar como root via cron)
rclone config create gdrive drive scope=drive.file \
  --non-interactive 2>/dev/null || true

echo ""
echo "  Agora autorizando acesso ao Google Drive..."
echo "  (uma URL será exibida — abra no navegador e autorize)"
echo ""
rclone authorize "drive" 2>/dev/null || \
  rclone config reconnect gdrive: 2>/dev/null || true

# Testa a conexão
echo ""
info "Testando conexão com o Google Drive..."
if rclone lsd gdrive: &>/dev/null; then
  log "Google Drive conectado com sucesso!"
else
  warn "Não foi possível verificar a conexão automaticamente."
  warn "Se o rclone config não foi concluído, rode manualmente: rclone config"
  warn "E configure um remote chamado 'gdrive' do tipo 'drive'."
fi

# ── cria pasta de backup local ─────────────────────────────────
mkdir -p /opt/imv-erp/backups
chmod 700 /opt/imv-erp/backups
log "Pasta de backup criada: /opt/imv-erp/backups"

# ── cria pasta no Google Drive ─────────────────────────────────
info "Criando pasta no Google Drive..."
rclone mkdir "gdrive:HN-Imoveis-ERP-Backups" 2>/dev/null && \
  log "Pasta 'HN-Imoveis-ERP-Backups' criada no Drive" || \
  warn "Pasta pode já existir — tudo certo"

# ── cron diário às 2h da manhã ────────────────────────────────
CRON_LINE="0 2 * * * root bash ${BACKUP_SCRIPT} --drive >> /var/log/imv-erp-backup.log 2>&1"
CRON_FILE="/etc/cron.d/imv-erp-backup"

cat > "$CRON_FILE" << CRONEOF
# HN Imóveis ERP — Backup automático diário às 02:00
# Envia para Google Drive e mantém cópia local (30 dias)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

${CRON_LINE}
CRONEOF

chmod 644 "$CRON_FILE"
log "Cron configurado: backup diário às 02:00 → Drive + local"

# ── cron semanal: limpa log do backup ────────────────────────
cat >> "$CRON_FILE" << 'CRONEOF2'

# Rotaciona log do backup semanalmente (todo domingo às 03:00)
0 3 * * 0 root [ -f /var/log/imv-erp-backup.log ] && tail -n 500 /var/log/imv-erp-backup.log > /var/log/imv-erp-backup.log.tmp && mv /var/log/imv-erp-backup.log.tmp /var/log/imv-erp-backup.log
CRONEOF2

# ── faz um backup inicial agora ───────────────────────────────
echo ""
info "Executando backup inicial (com upload para o Drive)..."
bash "$BACKUP_SCRIPT" --drive && \
  log "Backup inicial concluído!" || \
  warn "Backup inicial falhou — verifique as configurações acima"

# ── resultado ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${GREEN}${BOLD}   Setup de Backup Concluído!                  ${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""
echo -e "  ${BOLD}Backup automático:${NC} todo dia às ${YELLOW}02:00${NC}"
echo -e "  ${BOLD}Destino:${NC}          Google Drive → pasta ${YELLOW}HN-Imoveis-ERP-Backups${NC}"
echo -e "  ${BOLD}Cópia local:${NC}      ${YELLOW}/opt/imv-erp/backups/${NC} (30 dias)"
echo -e "  ${BOLD}Log:${NC}              ${YELLOW}/var/log/imv-erp-backup.log${NC}"
echo ""
echo -e "  ${BOLD}Comandos úteis:${NC}"
echo -e "  Backup manual agora:      ${YELLOW}sudo bash ${BACKUP_SCRIPT}${NC}"
echo -e "  Backup + enviar Drive:    ${YELLOW}sudo bash ${BACKUP_SCRIPT} --drive${NC}"
echo -e "  Ver log de backups:       ${YELLOW}tail -f /var/log/imv-erp-backup.log${NC}"
echo -e "  Ver backups locais:       ${YELLOW}ls -lh /opt/imv-erp/backups/${NC}"
echo -e "  Ver backups no Drive:     ${YELLOW}rclone ls gdrive:HN-Imoveis-ERP-Backups/${NC}"
echo ""
echo -e "  ${BOLD}Para restaurar um backup:${NC}"
echo -e "  ${YELLOW}gunzip -c /opt/imv-erp/backups/ARQUIVO.sql.gz | sudo -u postgres psql imv_erp${NC}"
echo ""
