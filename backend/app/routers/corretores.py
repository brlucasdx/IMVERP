from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.database import get_db
from app.models import Corretor, Cliente
from app.schemas import CorretorBase, CorretorUpdate, CorretorOut

router = APIRouter(prefix="/api/corretores", tags=["Corretores"])
router.dependencies.append(Depends(get_current_user))


@router.get("", response_model=list[CorretorOut])
def listar_corretores(db: Session = Depends(get_db)):
    rows = (
        db.query(Corretor, func.count(Cliente.id).label("cnt"))
        .outerjoin(Cliente, Cliente.corretor_id == Corretor.id)
        .filter(Corretor.ativo == True)
        .group_by(Corretor.id)
        .order_by(func.count(Cliente.id).desc())
        .all()
    )
    result = []
    for corretor, cnt in rows:
        out = CorretorOut.model_validate(corretor)
        out.total_vendas = cnt
        result.append(out)
    return result


@router.post("", response_model=CorretorOut, status_code=201)
def criar_corretor(payload: CorretorBase, db: Session = Depends(get_db)):
    corretor = Corretor(**payload.model_dump())
    db.add(corretor)
    db.commit()
    db.refresh(corretor)
    out = CorretorOut.model_validate(corretor)
    out.total_vendas = 0
    return out


@router.put("/{corretor_id}", response_model=CorretorOut)
def atualizar_corretor(corretor_id: int, payload: CorretorUpdate, db: Session = Depends(get_db)):
    corretor = db.get(Corretor, corretor_id)
    if not corretor:
        raise HTTPException(404, "Corretor não encontrado")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(corretor, campo, valor)
    db.commit()
    db.refresh(corretor)
    cnt = db.query(func.count(Cliente.id)).filter(Cliente.corretor_id == corretor_id).scalar() or 0
    out = CorretorOut.model_validate(corretor)
    out.total_vendas = cnt
    return out


@router.delete("/{corretor_id}", status_code=204)
def desativar_corretor(corretor_id: int, db: Session = Depends(get_db)):
    corretor = db.get(Corretor, corretor_id)
    if not corretor:
        raise HTTPException(404, "Corretor não encontrado")
    corretor.ativo = False
    db.commit()
