#!/bin/bash
# ============================================================
#  HN Imóveis ERP — Backup Manual do Banco de Dados
#  Uso: sudo bash backup.sh
#       sudo bash backup.sh --drive    (envia pro Google Drive)
# ============================================================

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[..] $1${NC}"; }
err()  { echo -e "${RED}[ERRO] $1${NC}"; exit 1; }

[ "$EUID" -ne 0 ] && err "Execute com sudo: sudo bash backup.sh"

# ── configurações ──────────────────────────────────────────────
ENV_FILE="/opt/imv-erp/backend/.env"
BACKUP_DIR="/opt/imv-erp/backups"
RETENTION_DAYS=30          # apaga backups com mais de 30 dias
RCLONE_REMOTE="gdrive"     # nome do remote rclone (configurado em setup_backup.sh)
RCLONE_FOLDER="HN-Imoveis-ERP-Backups"

# ── lê variáveis do .env ───────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  err "Arquivo .env não encontrado em $ENV_FILE"
fi

DB_NAME=$(grep '^DB_NAME'     "$ENV_FILE" | cut -d= -f2 | tr -d ' \r')
DB_USER=$(grep '^DB_USER'     "$ENV_FILE" | cut -d= -f2 | tr -d ' \r')
DB_PASSWORD=$(grep '^DB_PASSWORD' "$ENV_FILE" | cut -d= -f2 | tr -d ' \r')
DB_HOST=$(grep '^DB_HOST'     "$ENV_FILE" | cut -d= -f2 | tr -d ' \r')
DB_PORT=$(grep '^DB_PORT'     "$ENV_FILE" | cut -d= -f2 | tr -d ' \r')

[ -z "$DB_NAME" ] && err "DB_NAME não encontrado no .env"

# ── cria pasta de backup ───────────────────────────────────────
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="hn_erp_backup_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

echo ""
echo -e "${YELLOW}================================================${NC}"
echo -e "${YELLOW}   HN Imóveis ERP — Backup do Banco            ${NC}"
echo -e "${YELLOW}================================================${NC}"
echo ""
info "Banco: $DB_NAME @ $DB_HOST:$DB_PORT"
info "Destino: $FILEPATH"
echo ""

# ── dump comprimido ────────────────────────────────────────────
info "Executando pg_dump..."
PGPASSWORD="$DB_PASSWORD" pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --no-owner \
  --no-acl \
  -F plain \
  | gzip -9 > "$FILEPATH"

SIZE=$(du -sh "$FILEPATH" | cut -f1)
log "Backup criado: $FILENAME ($SIZE)"

# ── remove backups antigos (retenção local) ────────────────────
DELETED=$(find "$BACKUP_DIR" -name "hn_erp_backup_*.sql.gz" -mtime +${RETENTION_DAYS} -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "$DELETED backup(s) antigo(s) removido(s) (>${RETENTION_DAYS} dias)"

# ── upload para o Google Drive (opcional) ─────────────────────
SEND_TO_DRIVE=false
for arg in "$@"; do [ "$arg" = "--drive" ] && SEND_TO_DRIVE=true; done

if $SEND_TO_DRIVE; then
  if ! command -v rclone &>/dev/null; then
    echo -e "${YELLOW}[AVISO]${NC} rclone não instalado. Execute: sudo bash deploy/setup_backup.sh"
  else
    info "Enviando para Google Drive (${RCLONE_REMOTE}:${RCLONE_FOLDER})..."
    rclone copy "$FILEPATH" "${RCLONE_REMOTE}:${RCLONE_FOLDER}/" \
      --progress --stats-one-line 2>&1 || \
      echo -e "${YELLOW}[AVISO]${NC} Falha no upload para o Drive. Verifique rclone config."
    log "Upload para Google Drive concluído"

    # Limpa backups antigos do Drive também
    info "Limpando backups antigos do Google Drive (>${RETENTION_DAYS} dias)..."
    rclone delete "${RCLONE_REMOTE}:${RCLONE_FOLDER}/" \
      --min-age "${RETENTION_DAYS}d" 2>/dev/null || true
  fi
fi

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}   Backup concluído com sucesso!               ${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "  Arquivo: ${YELLOW}${FILEPATH}${NC}"
echo -e "  Tamanho: ${YELLOW}${SIZE}${NC}"
echo -e "  Backups locais em: ${YELLOW}${BACKUP_DIR}/${NC}"
echo ""
echo -e "  Para restaurar:"
echo -e "  ${YELLOW}gunzip -c $FILEPATH | sudo -u postgres psql $DB_NAME${NC}"
echo ""
