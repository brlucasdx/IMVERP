from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path

from app.database import engine, Base, settings
from app.routers import dashboard, clientes, corretores, rcpm, empreendimentos, analistas, comissoes, chaves, unidades, auth

# cria tabelas se não existirem
Base.metadata.create_all(bind=engine)

# cria pasta de uploads
Path(settings.UPLOAD_DIR).mkdir(exist_ok=True)

app = FastAPI(
    title="IMV ERP — API",
    description="Backend do sistema de Gestão Imobiliária",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
    return {"status": "ok", "version": "1.0.0"}

# Serve o frontend — procura o HTML relativo ao backend ou via variável de ambiente
import os as _os
_FRONTEND = Path(
    _os.environ.get("FRONTEND_PATH", "") or
    Path(__file__).parent.parent / "mockup_erp_imobiliario.html"
)

@app.get("/")
def frontend():
    if not _FRONTEND.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Frontend não encontrado"}, status_code=404)
    return FileResponse(_FRONTEND)
