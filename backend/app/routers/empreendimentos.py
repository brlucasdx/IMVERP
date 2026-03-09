from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.database import get_db
from app.models import Empreendimento, Cliente, Unidade
from app.schemas import EmpreendimentoOut, EmpreendimentoCreate, EmpreendimentoUpdate

router = APIRouter(prefix="/api/empreendimentos", tags=["Empreendimentos"])
router.dependencies.append(Depends(get_current_user))


def _build_out(emp: Empreendimento, cnt: int) -> EmpreendimentoOut:
    out = EmpreendimentoOut.model_validate(emp)
    out.total_clientes = cnt
    out.unidade_nome   = emp.unidade.nome   if emp.unidade else None
    out.unidade_cidade = emp.unidade.cidade if emp.unidade else None
    return out


@router.get("", response_model=list[EmpreendimentoOut])
def listar(
    unidade_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = (
        db.query(Empreendimento, func.count(Cliente.id).label("cnt"))
        .outerjoin(Cliente, (Cliente.empreendimento_id == Empreendimento.id) & (Cliente.ativo == True))
        .filter(Empreendimento.ativo == True)
    )
    if unidade_id:
        q = q.filter(Empreendimento.unidade_id == unidade_id)
    rows = q.group_by(Empreendimento.id).order_by(Empreendimento.nome).all()
    return [_build_out(emp, cnt) for emp, cnt in rows]


@router.post("", response_model=EmpreendimentoOut, status_code=201)
def criar(payload: EmpreendimentoCreate, db: Session = Depends(get_db)):
    if db.query(Empreendimento).filter(Empreendimento.nome == payload.nome).first():
        raise HTTPException(400, "Já existe um empreendimento com este nome")
    emp = Empreendimento(**payload.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _build_out(emp, 0)


@router.put("/{emp_id}", response_model=EmpreendimentoOut)
def atualizar(emp_id: int, payload: EmpreendimentoUpdate, db: Session = Depends(get_db)):
    emp = db.get(Empreendimento, emp_id)
    if not emp:
        raise HTTPException(404, "Empreendimento não encontrado")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(emp, campo, valor)
    db.commit()
    db.refresh(emp)
    cnt = db.query(func.count(Cliente.id)).filter(Cliente.empreendimento_id == emp_id, Cliente.ativo == True).scalar() or 0
    return _build_out(emp, cnt)


@router.delete("/{emp_id}", status_code=204)
def desativar(emp_id: int, db: Session = Depends(get_db)):
    emp = db.get(Empreendimento, emp_id)
    if not emp:
        raise HTTPException(404, "Empreendimento não encontrado")
    emp.ativo = False
    db.commit()
