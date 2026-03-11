# HN Imóveis ERP — Guia do Projeto

Sistema de gestão imobiliária (ERP) para a HN Imóveis, com backend FastAPI + PostgreSQL e frontend single-page HTML.

## Estrutura do Projeto

```
IMV/
├── backend/
│   ├── app/
│   │   ├── main.py              # Entry point FastAPI, registra todos os routers
│   │   ├── auth.py              # JWT (HS256) + bcrypt — get_current_user, require_admin
│   │   ├── database.py          # SQLAlchemy engine, get_db, Settings (pydantic-settings)
│   │   ├── models.py            # Todos os modelos ORM (SQLAlchemy)
│   │   ├── schemas.py           # Pydantic schemas de request/response
│   │   └── routers/
│   │       ├── auth.py          # /api/auth/* — login, gestão de usuários
│   │       ├── clientes.py      # /api/clientes/*
│   │       ├── chaves.py        # /api/chaves/* — liberar, concluir processo
│   │       ├── dashboard.py     # /api/dashboard/* — KPIs, relatórios, pipeline
│   │       ├── empreendimentos.py
│   │       ├── construtoras.py  # /api/construtoras/* — CRUD de construtoras (admin)
│   │       ├── corretores.py
│   │       ├── analistas.py
│   │       ├── comissoes.py
│   │       ├── rcpm.py
│   │       └── unidades.py      # /api/unidades/* — GET livre, mutações só admin
│   ├── ico/
│   │   └── Hn.png               # Logo HN Imóveis (embutido em base64 no HTML)
│   ├── mockup_erp_imobiliario.html  # Frontend SPA (servido pelo FastAPI em GET /)
│   ├── Procfile                 # Railway: uvicorn app.main:app --host 0.0.0.0 --port $PORT
│   ├── requirements.txt
│   ├── seed.py                  # Seed inicial de empreendimentos/clientes
│   └── seed_usuarios.py         # Seed de usuários (Adriella, Lucas, Simone, Markele)
├── mockup_erp_imobiliario.html  # Cópia em sync com backend/ (manter ambas iguais)
└── CLAUDE.md
```

## Como Rodar Localmente

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse: http://localhost:8000

## Variáveis de Ambiente

Arquivo `backend/.env`:
```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=imv_erp
DB_USER=imv_user
DB_PASSWORD=imv_senha_2024
SECRET_KEY=chave_super_secreta_producao   # OBRIGATÓRIO mudar em produção
UPLOAD_DIR=uploads
```

Em produção (Railway), usar `DATABASE_URL` direto:
```
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=...
ALLOWED_ORIGINS=https://imverp-production.up.railway.app
```

> **⚠️ `ALLOWED_ORIGINS` é obrigatório em produção.** Sem ela, o CORS cai para `["*"]` (qualquer origem).

## Segurança

- **`SecurityHeadersMiddleware`** em `main.py` injeta: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, `X-XSS-Protection`, `Referrer-Policy`
- **CORS** restrito via `ALLOWED_ORIGINS` env var — **nunca deixar sem definir em produção**
- **`BaseHTTPMiddleware`** deve ser importado de `starlette.middleware.base` (não `fastapi.middleware.base`)
- **Rate limit de login:** 5 tentativas/minuto por IP
- **Lixeira e Restaurar** exigem `require_admin` — operadores não têm acesso
- **Download de PDF:** filename sanitizado antes de ir para o header `Content-Disposition`
- **`UsuarioOut`** não expõe `created_at`

## Autenticação

- **JWT HS256**, expiração 8 horas
- **bcrypt rounds=12** para senhas
- Dois perfis: `admin` e `operador`
- Token enviado no header: `Authorization: Bearer <token>`

### Usuários do sistema
| Nome | Email | Tipo | Senha padrão |
|------|-------|------|--------------|
| Adriella | adriella@imv.com | admin | hn123 |
| Lucas | lucas@imv.com | admin | hn123 |
| Simone | simone@imv.com | operador | hn123 |
| Markele | markele@imv.com | operador | hn123 |
| Teste | teste@imv.com | admin | — (temporário, remover) |
| Jubileu teste | jubileu@imv.com | operador | — (temporário, remover) |

> **⚠️ Trocar as senhas padrão antes de ir a produção.**

## Permissões por Perfil

| Seção | Admin | Operador |
|-------|-------|----------|
| Dashboard | ✅ | ✅ |
| Processos (clientes) | ✅ | ✅ |
| Base (arquivados) | ✅ | ✅ |
| **Liberar Chaves** | ✅ | ✅ |
| Empreendimentos | ✅ | ✅ |
| Corretores | ✅ | ✅ |
| **Construtoras** | ✅ | ❌ |
| Unidades / Cidades | ✅ | ❌ |
| Financeiro (RCPM, Comissões) | ✅ | ❌ |
| Sistema (Relatórios, Lixeira, Config.) | ✅ | ❌ |

## Modelos Principais

### Hierarquia
```
Construtora (empresa parceira)
  └── Empreendimento (loteamento)  ← construtora_id FK + construtora string (legado)
        └── Cliente (processo imobiliário)

Unidade (filial/cidade) ──→ Empreendimento (unidade_id FK)
```

### Workflow do Cliente (7 etapas)
1. `engenharia` — Laudo do engenheiro
2. `aprovacao` — Aprovação de crédito / assinatura Caixa
3. `documentacao` — Certidões e pesquisas
4. `siktd` — Envio digital sistema Caixa (**display: SICTD** — chave interna `siktd` não alterar no BD)
5. `cartorio` — Cartório (autenticação física, 20-30 dias)
6. `entrega_chave` — Entrega da chave ao cliente ← **etapa adicionada**
7. `concluido` — Processo encerrado

**Regras de transição:**
- Só pode liberar chave se `doc_recebido = true` (ou `chave_rapida = true` no empreendimento)
- Ao liberar chave, workflow avança automaticamente para `entrega_chave` se ainda não chegou lá
- Só pode concluir após `chave_liberada = true`
- Só pode arquivar (Base) após `workflow_step == concluido` AND `chave_liberada = true`

**Migração necessária para `entrega_chave`:**
```sql
ALTER TYPE workflowstep ADD VALUE IF NOT EXISTS 'entrega_chave' AFTER 'cartorio';
```

### Campos do Cliente (principais)
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `num_ordem` | String | Número de ordem único |
| `cpf` | String | CPF único |
| `telefone` | String | Telefone do cliente |
| `workflow_step` | Enum | Etapa atual no workflow |
| `doc_recebido` | Boolean | Documento de garantia recebido |
| `chave_liberada` | Boolean | Chave física entregue |
| `data_chave_liberada` | Date | Data da entrega da chave |
| `arquivado` | Boolean | Movido para a Base |
| `arquivado_em` | DateTime | Data do arquivamento |

## Atenção: Migrations

`Base.metadata.create_all()` **NÃO altera tabelas existentes** — apenas cria novas.
Para adicionar colunas em tabelas já existentes, rodar SQL manual:
```sql
-- Workflow
ALTER TYPE workflowstep ADD VALUE IF NOT EXISTS 'entrega_chave' AFTER 'cartorio';

-- Colunas de clientes
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefone VARCHAR(20);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS chave_liberada BOOLEAN DEFAULT FALSE;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS data_chave_liberada DATE;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS arquivado BOOLEAN DEFAULT FALSE NOT NULL;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS arquivado_em TIMESTAMP;
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

-- PDFs dos clientes (múltiplos por cliente, armazenados como bytea)
CREATE TABLE IF NOT EXISTS cliente_pdfs (
  id SERIAL PRIMARY KEY,
  cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
  filename VARCHAR(255) NOT NULL,
  data BYTEA NOT NULL,
  tamanho INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Construtoras (nova entidade — executar UMA vez)
CREATE TABLE IF NOT EXISTS construtoras (
  id SERIAL PRIMARY KEY, nome VARCHAR(120) NOT NULL UNIQUE,
  cnpj VARCHAR(18), telefone VARCHAR(20), email VARCHAR(150),
  responsavel VARCHAR(120), ativo BOOLEAN DEFAULT TRUE
);
UPDATE construtoras SET ativo = TRUE WHERE ativo IS NULL;
ALTER TABLE construtoras ALTER COLUMN ativo SET NOT NULL;
ALTER TABLE empreendimentos ADD COLUMN IF NOT EXISTS construtora_id INTEGER REFERENCES construtoras(id);
-- Auto-migrar dados existentes:
INSERT INTO construtoras (nome, ativo)
  SELECT DISTINCT construtora, TRUE FROM empreendimentos
  WHERE construtora IS NOT NULL AND construtora <> ''
  ON CONFLICT (nome) DO NOTHING;
UPDATE empreendimentos e SET construtora_id = c.id
  FROM construtoras c WHERE e.construtora = c.nome AND e.construtora_id IS NULL;
```

**Atenção:** `create_all` pode criar a tabela `construtoras` sem NOT NULL no campo `ativo` — sempre rodar o `UPDATE + ALTER` acima para garantir consistência.

## API Endpoints Principais

### Clientes (`/api/clientes`)
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Listar processos (filtros: busca, empreendimento, analista, unidade, status, arquivados) |
| POST | `/` | Criar cliente |
| GET | `/{id}` | Buscar cliente |
| PUT | `/{id}` | Atualizar cliente (com log automático por campo alterado) |
| DELETE | `/{id}` | Soft-delete (lixeira) |
| POST | `/{id}/arquivar` | Mover para Base (requer concluido + chave entregue) |
| POST | `/{id}/desarquivar` | Voltar para Processos |
| POST | `/{id}/restaurar` | Restaurar da lixeira (admin) |
| POST | `/{id}/upload` | Upload de PDF (até 5 arquivos simultâneos, 5 MB cada) |
| GET | `/{id}/pdfs` | Listar PDFs do cliente |
| GET | `/{id}/pdfs/{pdf_id}` | Download de PDF |
| DELETE | `/{id}/pdfs/{pdf_id}` | Excluir PDF (admin) |
| GET | `/{id}/logs` | Histórico de atividades |
| GET | `/{id}/notas` | Notas do processo |
| POST | `/{id}/notas` | Adicionar nota |
| DELETE | `/notas/{nota_id}` | Excluir nota (admin ou autor) |

### Chaves (`/api/chaves`)
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Listar processos com controle de chave (`?apenas_pendentes=true`) |
| POST | `/{id}/liberar` | Liberar chave (registra data, avança para entrega_chave) |
| POST | `/{id}/concluir` | Concluir processo (requer chave liberada) |

### Construtoras (`/api/construtoras`)
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Listar construtoras ativas com total de empreendimentos |
| POST | `/` | Criar construtora |
| PUT | `/{id}` | Atualizar construtora |
| DELETE | `/{id}` | Desativar construtora (soft) |

### RCPM (`/api/rcpm`)
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/conciliacao` | Totais por empreendimento (apólices, valor RCPM, em cartório, atrasados) |
| GET | `/em-cartorio` | Clientes atualmente em `workflow_step=cartorio` com urgência calculada |
| GET | `/vencimentos` | Clientes com `chegada_cartorio` preenchida e situação calculada |

### Dashboard (`/api/dashboard`)
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | KPIs, funil, ranking, alertas cartório |
| GET | `/relatorio-mensal?mes=YYYY-MM` | Relatório mensal por empreendimento + ranking |
| GET | `/relatorio-semanal?semana=YYYY-Wnn` | Relatório semanal (ex: 2026-W10) |
| GET | `/relatorio-corretores?mes=YYYY-MM` | Performance por corretor no período |
| GET | `/pipeline-duracao` | Média de dias por etapa do workflow (gargalos) |

## Frontend (SPA em HTML único)

- Arquivo: `backend/mockup_erp_imobiliario.html`
- Servido pelo FastAPI em `GET /`
- Modal system: usa classe `.open` (não `.active`)
- Auth: token no `localStorage` com chave `imv_token`, usuário em `imv_user`
- Role-based UI: `body.is-admin` habilita elementos `[data-role="admin"]`
- `apiFetch()` injeta Bearer token automaticamente + trata 401/403
- Relógio ao vivo no topbar: `id="topbar-clock"`, atualizado a cada 10s via `setInterval`

### Branding HN Imóveis
- Logo `ico/Hn.png` embutido como base64 em 3 locais: sidebar, tela de login, cabeçalho de impressão
- Favicon da aba do browser também usa o logo base64
- Título: `<title>HN Imóveis — ERP</title>`
- Cores do logo: fundo preto, letras brancas + amarelo `#f5c518`

### Seções do Frontend
| Página | ID | Acesso | Descrição |
|--------|----|--------|-----------|
| Dashboard | `page-dashboard` | Todos | KPIs, funil, ranking, alertas |
| Processos | `page-clientes` | Todos | Lista/edição de clientes (tabela ou cards) |
| Base | `page-base` | Todos | Processos arquivados com filtro de data |
| Liberar Chaves | `page-chaves` | Todos | Cards com ações por status (apto/aguardando/liberada) |
| Empreendimentos | `page-empreendimentos` | Todos | CRUD de empreendimentos + vínculo com construtora |
| **Construtoras** | `page-construtoras` | Admin | CRUD de construtoras (nome, CNPJ, telefone, email, responsável) |
| Corretores | `page-corretores` | Todos | KPIs, ranking e gestão de corretores |
| Unidades | `page-unidades` | Admin | CRUD de unidades/cidades |
| Relatórios | `page-relatorios` | Admin | KPIs mensal/semanal + corretores + pipeline |
| Comissões | `page-comissoes` | Admin | Auto-calculado por assinaturas + lançamentos manuais |
| RCPM | `page-rcpm` | Admin | 3 abas: Visão Geral (agrupado por construtora), Em Cartório Agora (cards), Vencimentos |
| Configurações | `page-configuracoes` | Admin | Gestão de usuários |
| Lixeira | `page-lixeira` | Admin | Soft-deleted |

### Notas dos Processos
- Exibidas diretamente no modal de edição (acima de Observações)
- Apenas **admin** pode excluir notas (operadores só visualizam e adicionam)
- Log automático ao adicionar nota com preview do texto (120 chars)

### Relatório de Pipeline
- Seção "Análise de Pipeline — Tempo por Etapa" na página de Relatórios
- Barras horizontais coloridas por etapa com média de dias
- Alerta automático de gargalo (etapa com maior média > 5 dias)
- Tabela com: processos, média, mínimo, máximo, status (Rápido/Normal/Gargalo)
- Baseado nos logs reais de transição `workflow_alterado`

## Logs de Atividade

Cada ação relevante gera um `LogAtividade` com `acao` padronizado:

| `acao` | Gerado quando |
|--------|---------------|
| `cliente_criado` | Novo processo cadastrado |
| `workflow_alterado` | Etapa do workflow muda (formato: `"etapa_anterior → etapa_nova"`) |
| `doc_recebido` | Documento de garantia marcado como recebido |
| `chave_liberada` | Chave física entregue ao cliente |
| `arquivado` | Processo movido para Base |
| `desarquivado` | Processo devolvido para Processos |
| `dados_atualizados` | Campos alterados (só loga campos que realmente mudaram) |
| `nota_adicionada` | Nova nota com preview do texto |
| `pdf_enviado` | Contrato PDF enviado |

**Importante:** o backend compara valores antes/depois de `setattr` para evitar logs espúrios.
Normalização para comparação: `enum.value` e `Decimal` como string.

## Deploy (Railway)

1. Conectar GitHub → apontar root para `backend/`
2. Adicionar PostgreSQL plugin
3. Variáveis de ambiente: `DATABASE_URL` (auto), `SECRET_KEY`
4. Procfile já configurado: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### Atualizar produção (novo deploy)
Basta fazer `git push origin main` — o Railway detecta automaticamente e redeploya.

**Se a atualização mexeu no banco (nova coluna/tabela):** rodar SQL manual no Railway:
1. Acessa `railway.app` → projeto → serviço **Postgres**
2. Aba **Database** → clica em **"Query"**
3. Cola o SQL e executa

Exemplos:
```sql
-- Nova coluna
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS novo_campo VARCHAR(100);

-- Nova tabela
CREATE TABLE IF NOT EXISTS nova_tabela (...);

-- Novo valor em enum
ALTER TYPE workflowstep ADD VALUE IF NOT EXISTS 'novo_step' AFTER 'anterior';
```

> **Sempre usar `IF NOT EXISTS`** para evitar erro se rodar duas vezes.
> `create_all()` do SQLAlchemy **NÃO altera tabelas existentes** — sempre usar ALTER TABLE manual.

### URL de produção
`https://imverp-production.up.railway.app`

### Backup automático
- GitHub Actions roda todo dia às 02h00 BRT
- Destino: Google Drive → pasta `Backups/IMVERP/`
- Retenção: 30 dias
- Workflow: `.github/workflows/backup.yml`

### Plano de contingência (Railway fora do ar)
```bash
cd "/home/lucas/Documentos/lusca (2)/Pessoal/IMV/backend"

# 1. Limpar banco local
PGPASSWORD=imv_senha_2024 psql -U imv_user -h localhost -d imv_erp -c \
"TRUNCATE TABLE notas_clientes, logs_atividade, comissao_lancamentos, clientes, \
empreendimentos, construtoras, analistas, corretores, unidades, usuarios \
RESTART IDENTITY CASCADE;"

# 2. Restaurar backup (baixar do Google Drive o arquivo mais recente)
gunzip -c imverp_backup_YYYY-MM-DD.sql.gz | \
PGPASSWORD=imv_senha_2024 psql -U imv_user -h localhost -d imv_erp

# 3. Subir local
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Pacotes Principais

```
fastapi, uvicorn, sqlalchemy, psycopg2-binary
pydantic, pydantic-settings
bcrypt==4.2.1, python-jose[cryptography]==3.3.0
python-multipart, alembic
```
