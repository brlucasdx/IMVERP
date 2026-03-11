from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.database import get_db
from app.models import Cliente, LogAtividade, Usuario
from app.schemas import LogSistemaOut

router = APIRouter(prefix="/api/logs", tags=["Logs"])
router.dependencies.append(Depends(require_admin))


@router.get("", response_model=list[LogSistemaOut])
def listar_logs(
    busca: str = Query(default="", description="Filtrar por nome do cliente ou detalhes"),
    acao: str = Query(default="", description="Filtrar por tipo de ação"),
    usuario_id: int = Query(default=None, description="Filtrar por usuário"),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(LogAtividade)
        .options(joinedload(LogAtividade.cliente), joinedload(LogAtividade.usuario))
        .join(Cliente, LogAtividade.cliente_id == Cliente.id)
        .order_by(LogAtividade.created_at.desc())
    )

    if acao:
        q = q.filter(LogAtividade.acao == acao)
    if usuario_id:
        q = q.filter(LogAtividade.usuario_id == usuario_id)
    if busca:
        termo = f"%{busca}%"
        q = q.filter(
            Cliente.nome.ilike(termo) | LogAtividade.detalhes.ilike(termo)
        )

    rows = q.offset(offset).limit(limit).all()

    return [
        LogSistemaOut(
            id=l.id,
            cliente_id=l.cliente_id,
            cliente_nome=l.cliente.nome if l.cliente else "?",
            usuario_nome=l.usuario.nome if l.usuario else "Sistema",
            acao=l.acao,
            detalhes=l.detalhes,
            created_at=l.created_at,
        )
        for l in rows
    ]


@router.get("/acoes", response_model=list[str])
def listar_acoes(db: Session = Depends(get_db)):
    """Retorna os tipos de ação distintos existentes nos logs."""
    rows = db.query(LogAtividade.acao).distinct().order_by(LogAtividade.acao).all()
    return [r[0] for r in rows]
