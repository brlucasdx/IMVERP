#!/bin/bash
# ============================================================
#  IMV ERP — Script de Deploy para Ubuntu 22.04 / 24.04
#  Servidor local Linux + Nginx
#  Uso: sudo bash deploy.sh
# ============================================================

set -e  # para na primeira falha

# ---- cores ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
info() { echo -e "${BLUE}[..] $1${NC}"; }
warn() { echo -e "${YELLOW}[!!] $1${NC}"; }
err()  { echo -e "${RED}[ERRO] $1${NC}"; exit 1; }

# ---- verifica root ----
[ "$EUID" -ne 0 ] && err "Execute com sudo: sudo bash deploy.sh"

# ---- configurações ----
APP_DIR="/var/www/imv-erp"
NGINX_CONF="/etc/nginx/sites-available/imv-erp"
NGINX_ENABLED="/etc/nginx/sites-enabled/imv-erp"
HTML_FILE="$(dirname "$0")/../mockup_erp_imobiliario.html"

echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${BOLD}   IMV ERP — Deploy em Produção (Ubuntu/Nginx)  ${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""

# ---- 1. atualiza pacotes ----
info "Atualizando lista de pacotes..."
apt-get update -qq
log "Pacotes atualizados"

# ---- 2. instala nginx ----
if ! command -v nginx &>/dev/null; then
  info "Instalando Nginx..."
  apt-get install -y -qq nginx
  log "Nginx instalado"
else
  log "Nginx já instalado ($(nginx -v 2>&1 | grep -o '[0-9.]*$'))"
fi

# ---- 3. instala ufw (firewall) ----
if ! command -v ufw &>/dev/null; then
  info "Instalando UFW (firewall)..."
  apt-get install -y -qq ufw
fi

# ---- 4. cria diretório da aplicação ----
info "Criando diretório $APP_DIR..."
mkdir -p "$APP_DIR"
log "Diretório criado"

# ---- 5. copia o HTML ----
if [ -f "$HTML_FILE" ]; then
  cp "$HTML_FILE" "$APP_DIR/index.html"
  log "Arquivo HTML copiado para $APP_DIR/index.html"
else
  warn "Arquivo HTML não encontrado em $HTML_FILE"
  warn "Coloque o arquivo manualmente: cp mockup_erp_imobiliario.html $APP_DIR/index.html"
fi

# ---- 6. define permissões ----
chown -R www-data:www-data "$APP_DIR"
chmod -R 755 "$APP_DIR"
log "Permissões configuradas"

# ---- 7. detecta IP local ----
LOCAL_IP=$(hostname -I | awk '{print $1}')

# ---- 8. cria config do Nginx ----
info "Configurando Nginx..."
cat > "$NGINX_CONF" << EOF
server {
    listen 80;
    listen [::]:80;

    server_name $LOCAL_IP _;

    root $APP_DIR;
    index index.html;

    # logs
    access_log /var/log/nginx/imv-erp-access.log;
    error_log  /var/log/nginx/imv-erp-error.log;

    # headers de segurança
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";

    # cache para assets estáticos
    location ~* \.(html|css|js|ico|png|jpg|svg)$ {
        expires 1h;
        add_header Cache-Control "public";
    }

    # rota principal
    location / {
        try_files \$uri \$uri/ /index.html;
    }

    # bloqueia acesso a arquivos ocultos
    location ~ /\. {
        deny all;
    }
}
EOF
log "Config do Nginx criada"

# ---- 9. ativa o site ----
ln -sf "$NGINX_CONF" "$NGINX_ENABLED"

# remove o site default se existir
[ -f /etc/nginx/sites-enabled/default ] && rm -f /etc/nginx/sites-enabled/default && log "Site default do Nginx removido"

# ---- 10. valida config do nginx ----
info "Validando configuração do Nginx..."
nginx -t 2>/dev/null || err "Configuração do Nginx inválida. Verifique: nginx -t"
log "Configuração do Nginx válida"

# ---- 11. habilita e inicia Nginx ----
info "Habilitando Nginx para iniciar com o sistema..."
systemctl enable nginx -q
systemctl restart nginx
log "Nginx reiniciado e habilitado no boot"

# ---- 12. configura firewall ----
info "Configurando firewall UFW..."
ufw allow 'Nginx HTTP' -q 2>/dev/null || ufw allow 80/tcp -q
ufw --force enable -q 2>/dev/null || true
log "Porta 80 liberada no firewall"

# ---- 13. verifica se está respondendo ----
sleep 1
if curl -s -o /dev/null -w "%{http_code}" "http://localhost" | grep -q "200"; then
  log "Nginx respondendo corretamente na porta 80"
else
  warn "Nginx pode não estar respondendo ainda — verifique: systemctl status nginx"
fi

# ---- resultado ----
echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${GREEN}${BOLD}   DEPLOY CONCLUÍDO COM SUCESSO!${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""
echo -e "  ${BOLD}Acesse o sistema em:${NC}"
echo -e "  ${BLUE}${BOLD}http://$LOCAL_IP${NC}"
echo ""
echo -e "  ${BOLD}Comandos úteis:${NC}"
echo -e "  Reiniciar Nginx:   ${YELLOW}sudo systemctl restart nginx${NC}"
echo -e "  Status do Nginx:   ${YELLOW}sudo systemctl status nginx${NC}"
echo -e "  Log de acesso:     ${YELLOW}sudo tail -f /var/log/nginx/imv-erp-access.log${NC}"
echo -e "  Log de erro:       ${YELLOW}sudo tail -f /var/log/nginx/imv-erp-error.log${NC}"
echo -e "  Atualizar HTML:    ${YELLOW}sudo cp mockup_erp_imobiliario.html $APP_DIR/index.html${NC}"
echo ""
