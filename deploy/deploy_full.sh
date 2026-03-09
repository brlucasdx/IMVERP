#!/bin/bash
# ============================================================
#  HN Imóveis ERP — Deploy COMPLETO em Produção
#  Instala: Nginx + PostgreSQL + FastAPI + systemd
#  Uso: sudo bash deploy_full.sh
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[..] $1${NC}"; }
err()  { echo -e "${RED}[ERRO] $1${NC}"; exit 1; }

[ "$EUID" -ne 0 ] && err "Execute com sudo: sudo bash deploy_full.sh"

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="/opt/imv-erp"
APP_STATIC="/var/www/imv-erp"
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${BOLD}   HN Imóveis ERP — Deploy Completo             ${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""

# ── dependências ──────────────────────────────────────────────
info "Instalando dependências do sistema..."
apt-get update -qq
apt-get install -y -qq nginx python3 python3-venv python3-pip postgresql postgresql-contrib libpq-dev ufw
log "Dependências instaladas"

# ── PostgreSQL ─────────────────────────────────────────────────
info "Configurando PostgreSQL..."
systemctl enable postgresql -q
systemctl start postgresql

DB_NAME="imv_erp"
DB_USER="imv_user"
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(20))")

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null
log "PostgreSQL configurado"

# ── copia código para /opt ─────────────────────────────────────
info "Instalando aplicação em $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
rsync -a --exclude='venv' --exclude='__pycache__' --exclude='uploads' \
  "$REPO_DIR/backend/" "$INSTALL_DIR/backend/"
log "Código copiado"

# ── .env em produção ──────────────────────────────────────────
cat > "$INSTALL_DIR/backend/.env" << ENVEOF
DB_HOST=localhost
DB_PORT=5432
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
API_PORT=8000
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
UPLOAD_DIR=${INSTALL_DIR}/backend/uploads
ENVEOF
log ".env de produção criado"

# ── venv + pacotes ─────────────────────────────────────────────
info "Criando venv e instalando pacotes Python..."
python3 -m venv "$INSTALL_DIR/backend/venv"
"$INSTALL_DIR/backend/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/backend/venv/bin/pip" install --quiet -r "$INSTALL_DIR/backend/requirements.txt"
log "Pacotes Python instalados"

# ── init banco + seed ──────────────────────────────────────────
info "Criando tabelas e dados de exemplo..."
mkdir -p "$INSTALL_DIR/backend/uploads"
cd "$INSTALL_DIR/backend"
"$INSTALL_DIR/backend/venv/bin/python" -c "
from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
"
log "Tabelas criadas"

# ── migrações incrementais (seguras p/ novo install e p/ upgrade) ──────────
info "Aplicando migrações de schema..."
sudo -u postgres psql -d "${DB_NAME}" << 'SQLEOF'
-- Enum: adiciona etapa entrega_chave se ainda não existir
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'entrega_chave'
      AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'workflowstep')
  ) THEN
    ALTER TYPE workflowstep ADD VALUE 'entrega_chave' AFTER 'cartorio';
  END IF;
END$$;

-- Coluna telefone no cliente (adicionada em v2)
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefone VARCHAR(20);

-- Colunas de arquivamento
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS arquivado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS arquivado_em TIMESTAMP;

-- Colunas de chave
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS chave_liberada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS data_chave_liberada DATE;

-- Soft-delete
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- Tabela de notas (criada pelo create_all; garante existência)
CREATE TABLE IF NOT EXISTS notas_clientes (
  id         SERIAL PRIMARY KEY,
  cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
  texto      TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
SQLEOF
log "Migrações aplicadas"

info "Rodando seed de dados iniciais..."
"$INSTALL_DIR/backend/venv/bin/python" seed.py
log "Banco inicializado"

# ── permissões ─────────────────────────────────────────────────
chown -R www-data:www-data "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
log "Permissões configuradas"

# ── frontend estático ─────────────────────────────────────────
info "Configurando frontend..."
mkdir -p "$APP_STATIC"
cp "$REPO_DIR/mockup_erp_imobiliario.html" "$APP_STATIC/index.html"
chown -R www-data:www-data "$APP_STATIC"
log "Frontend copiado para $APP_STATIC"

# ── systemd service ────────────────────────────────────────────
info "Instalando serviço systemd..."
cp "$REPO_DIR/deploy/imv-erp.service" /etc/systemd/system/
# ajusta path no service file
sed -i "s|/opt/imv-erp|${INSTALL_DIR}|g" /etc/systemd/system/imv-erp.service
systemctl daemon-reload
systemctl enable imv-erp
systemctl restart imv-erp
sleep 2
systemctl is-active --quiet imv-erp && log "Serviço FastAPI ativo" || \
  { echo ""; journalctl -u imv-erp -n 20 --no-pager; err "Serviço não iniciou"; }

# ── Nginx ──────────────────────────────────────────────────────
info "Configurando Nginx..."
cat > /etc/nginx/sites-available/imv-erp << NGINXEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${LOCAL_IP} _;

    root ${APP_STATIC};
    index index.html;

    access_log /var/log/nginx/imv-erp-access.log;
    error_log  /var/log/nginx/imv-erp-error.log;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    # Proxy para o FastAPI
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host \$host;
        proxy_set_header   X-Real-IP \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
        client_max_body_size 20M;
    }

    # Frontend estático
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location ~ /\. { deny all; }
}
NGINXEOF

ln -sf /etc/nginx/sites-available/imv-erp /etc/nginx/sites-enabled/imv-erp
[ -f /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default
nginx -t 2>/dev/null || err "Configuração do Nginx inválida"
systemctl enable nginx -q
systemctl restart nginx
log "Nginx configurado e reiniciado"

# ── firewall ───────────────────────────────────────────────────
ufw allow 'Nginx HTTP' -q 2>/dev/null || ufw allow 80/tcp -q
ufw --force enable -q 2>/dev/null || true
log "Firewall configurado"

# ── resultado ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${GREEN}${BOLD}   HN Imóveis ERP — DEPLOY CONCLUÍDO!          ${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""
echo -e "  ${BOLD}Sistema:${NC}  ${BLUE}${BOLD}http://${LOCAL_IP}${NC}"
echo -e "  ${BOLD}API Docs:${NC} ${BLUE}http://${LOCAL_IP}/api/docs${NC}"
echo ""
echo -e "  ${BOLD}Banco de dados:${NC}"
echo -e "  Nome:    ${YELLOW}${DB_NAME}${NC}"
echo -e "  Usuário: ${YELLOW}${DB_USER}${NC}"
echo -e "  Senha:   salva em ${YELLOW}${INSTALL_DIR}/backend/.env${NC}"
echo ""
echo -e "  ${BOLD}Login padrão:${NC}"
echo -e "  Admin:    ${YELLOW}admin@hnimóveis.com${NC}  /  ${YELLOW}admin${NC}"
echo ""
echo -e "  ${BOLD}Comandos úteis:${NC}"
echo -e "  Status API:    ${YELLOW}sudo systemctl status imv-erp${NC}"
echo -e "  Log API:       ${YELLOW}sudo journalctl -u imv-erp -f${NC}"
echo -e "  Log Nginx:     ${YELLOW}sudo tail -f /var/log/nginx/imv-erp-access.log${NC}"
echo -e "  Reiniciar:     ${YELLOW}sudo systemctl restart imv-erp nginx${NC}"
echo -e "  Atualizar:     ${YELLOW}cd ~/IMVERP && git pull && sudo bash deploy/atualizar.sh${NC}"
echo ""
