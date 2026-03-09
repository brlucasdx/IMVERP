import os as _os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import engine, Base, settings
from app.routers import dashboard, clientes, corretores, rcpm, empreendimentos, analistas, comissoes, chaves, unidades, auth

# ── rate limiter global ────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# cria tabelas se não existirem
Base.metadata.create_all(bind=engine)

# cria pasta de uploads
Path(settings.UPLOAD_DIR).mkdir(exist_ok=True)

# ── CORS: em produção, restringir ao próprio domínio via env var ──────────────
_raw_origins = _os.environ.get("ALLOWED_ORIGINS", "")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] or ["*"]

app = FastAPI(
    title="HN Imóveis ERP — API",
    description="Backend do sistema de Gestão de Processos Imobiliários",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(clientes.router)
app.include_router(corretores.router)
app.include_router(rcpm.router)
app.include_router(empreendimentos.router)
app.include_router(analistas.router)
app.include_router(comissoes.router)
app.include_router(chaves.router)
app.include_router(unidades.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# Serve o frontend
_FRONTEND = Path(
    _os.environ.get("FRONTEND_PATH", "") or
    Path(__file__).parent.parent / "mockup_erp_imobiliario.html"
)


@app.get("/")
def frontend():
    if not _FRONTEND.exists():
        return JSONResponse({"detail": "Frontend não encontrado"}, status_code=404)
    return FileResponse(_FRONTEND)
