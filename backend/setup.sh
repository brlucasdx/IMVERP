#!/bin/bash
# ============================================================
#  IMV ERP — Setup do Backend (Python venv + PostgreSQL)
#  Uso: bash setup.sh
#  Execute na pasta: IMV/backend/
# ============================================================

set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[..] $1${NC}"; }
warn() { echo -e "${YELLOW}[!!] $1${NC}"; }
err()  { echo -e "${RED}[ERRO] $1${NC}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${BOLD}   IMV ERP — Setup do Backend                   ${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""

# ── 1. dependências do sistema ─────────────────────────────────
info "Verificando dependências do sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip postgresql postgresql-contrib libpq-dev
log "Dependências do sistema instaladas"

# ── 2. PostgreSQL ──────────────────────────────────────────────
info "Configurando PostgreSQL..."
sudo systemctl enable postgresql -q
sudo systemctl start postgresql
log "PostgreSQL iniciado"

# lê credenciais do .env ou usa padrões
DB_NAME="imv_erp"
DB_USER="imv_user"
DB_PASSWORD="imv_senha_2024"

if [ -f ".env" ]; then
  DB_NAME=$(grep "^DB_NAME=" .env | cut -d= -f2 | tr -d '"' || echo "imv_erp")
  DB_USER=$(grep "^DB_USER=" .env | cut -d= -f2 | tr -d '"' || echo "imv_user")
  DB_PASSWORD=$(grep "^DB_PASSWORD=" .env | cut -d= -f2 | tr -d '"' || echo "imv_senha_2024")
fi

# cria usuário e banco
sudo -u postgres psql -c "
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
      CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';
    END IF;
  END
  \$\$;
" 2>/dev/null
sudo -u postgres psql -c "
  SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')
" 2>/dev/null | sudo -u postgres psql 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};" 2>/dev/null
log "Banco '${DB_NAME}' e usuário '${DB_USER}' prontos"

# ── 3. arquivo .env ────────────────────────────────────────────
if [ ! -f ".env" ]; then
  info "Criando arquivo .env..."
  cat > .env << ENVEOF
DB_HOST=localhost
DB_PORT=5432
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
API_PORT=8000
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
UPLOAD_DIR=uploads
ENVEOF
  log ".env criado"
else
  log ".env já existe — mantendo configurações atuais"
fi

# ── 4. venv ────────────────────────────────────────────────────
info "Criando ambiente virtual Python..."
python3 -m venv venv
log "venv criado em ./venv"

# ── 5. instala dependências Python ────────────────────────────
info "Instalando pacotes Python..."
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt
log "Pacotes instalados"

# ── 6. cria pasta de uploads ───────────────────────────────────
mkdir -p uploads
log "Pasta uploads/ criada"

# ── 7. inicializa banco (tabelas) ──────────────────────────────
info "Criando tabelas no banco de dados..."
./venv/bin/python -c "
from app.database import engine, Base
import app.models
Base.metadata.create_all(bind=engine)
print('Tabelas criadas.')
"
log "Tabelas criadas"

# ── 8. seed (dados de exemplo) ─────────────────────────────────
info "Populando com dados de exemplo..."
./venv/bin/python seed.py
log "Dados de exemplo inseridos"

# ── 9. resultado ───────────────────────────────────────────────
echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${GREEN}${BOLD}   SETUP CONCLUÍDO!${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""
echo -e "  Para iniciar o servidor de desenvolvimento:"
echo -e "  ${YELLOW}cd backend && source venv/bin/activate${NC}"
echo -e "  ${YELLOW}uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload${NC}"
echo ""
echo -e "  Documentação da API (após iniciar):"
echo -e "  ${BLUE}http://localhost:8000/api/docs${NC}"
echo ""
echo -e "  Para instalar como serviço em produção:"
echo -e "  ${YELLOW}sudo bash ../deploy/deploy_full.sh${NC}"
echo ""
