from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Cliente, Empreendimento, Unidade, Usuario
from app.schemas import UnidadeCreate, UnidadeOut, UnidadeUpdate

# GET acessível a qualquer usuário autenticado (usado nos dropdowns)
# POST/PUT/DELETE requer admin (ver cada rota)
router = APIRouter(prefix="/api/unidades", tags=["Unidades"])
router.dependencies.append(Depends(get_current_user))


def _to_out(u: Unidade, db: Session) -> UnidadeOut:
    total_emp = (
        db.query(func.count(Empreendimento.id))
        .filter(Empreendimento.unidade_id == u.id, Empreendimento.ativo == True)
        .scalar() or 0
    )
    total_cli = (
        db.query(func.count(Cliente.id))
        .join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)
        .filter(Empreendimento.unidade_id == u.id, Cliente.ativo == True)
        .scalar() or 0
    )
    return UnidadeOut(
        id=u.id,
        nome=u.nome,
        cidade=u.cidade,
        estado=u.estado,
        ativo=u.ativo,
        total_empreendimentos=total_emp,
        total_clientes=total_cli,
    )


@router.get("", response_model=list[UnidadeOut])
def listar(db: Session = Depends(get_db)):
    unidades = db.query(Unidade).filter(Unidade.ativo == True).order_by(Unidade.nome).all()
    return [_to_out(u, db) for u in unidades]


@router.post("", response_model=UnidadeOut, status_code=201)
def criar(payload: UnidadeCreate, db: Session = Depends(get_db), _: Usuario = Depends(require_admin)):
    u = Unidade(**payload.model_dump())
    db.add(u)
    db.commit()
    db.refresh(u)
    return _to_out(u, db)


@router.put("/{unidade_id}", response_model=UnidadeOut)
def atualizar(unidade_id: int, payload: UnidadeUpdate, db: Session = Depends(get_db), _: Usuario = Depends(require_admin)):
    u = db.get(Unidade, unidade_id)
    if not u or not u.ativo:
        raise HTTPException(404, "Unidade não encontrada")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(u, campo, valor)
    db.commit()
    db.refresh(u)
    return _to_out(u, db)


@router.delete("/{unidade_id}", status_code=204)
def desativar(unidade_id: int, db: Session = Depends(get_db), _: Usuario = Depends(require_admin)):
    u = db.get(Unidade, unidade_id)
    if not u or not u.ativo:
        raise HTTPException(404, "Unidade não encontrada")
    u.ativo = False
    db.commit()
