from typing import Any
from sqlalchemy.orm import Session, joinedload
from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.database import get_db
from app.models import Construtora, Empreendimento
from app.schemas import ConstrutoraCriar, ConstrutorUpdate, ConstrutorOut

router = APIRouter(prefix="/api/construtoras", tags=["Construtoras"])
router.dependencies.append(Depends(get_current_user))


def _build_out(c: Construtora) -> dict:
    emps = [e for e in c.empreendimentos if e.ativo]
    return {
        "id": c.id,
        "nome": c.nome,
        "cnpj": c.cnpj,
        "telefone": c.telefone,
        "email": c.email,
        "responsavel": c.responsavel,
        "ativo": c.ativo,
        "total_empreendimentos": len(emps),
        "empreendimentos_nomes": sorted(e.nome for e in emps),
    }


@router.get("")
def listar(db: Session = Depends(get_db)) -> Any:
    construtoras = (
        db.query(Construtora)
        .options(joinedload(Construtora.empreendimentos))
        .filter(Construtora.ativo == True)
        .order_by(Construtora.nome)
        .all()
    )
    return [_build_out(c) for c in construtoras]


@router.post("", status_code=201)
def criar(payload: ConstrutoraCriar, db: Session = Depends(get_db)) -> Any:
    if db.query(Construtora).filter(Construtora.nome == payload.nome.strip()).first():
        raise HTTPException(400, "Já existe uma construtora com este nome")
    dados = {k: v.strip() if isinstance(v, str) else v
             for k, v in payload.model_dump().items() if v is not None}
    c = Construtora(**dados)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _build_out(c)


@router.put("/{cid}")
def atualizar(cid: int, payload: ConstrutorUpdate, db: Session = Depends(get_db)) -> Any:
    c = db.query(Construtora).options(joinedload(Construtora.empreendimentos)).filter(Construtora.id == cid).first()
    if not c:
        raise HTTPException(404, "Construtora não encontrada")
    for campo, valor in payload.model_dump(exclude_none=True).items():
        setattr(c, campo, valor.strip() if isinstance(valor, str) else valor)
    db.commit()
    db.refresh(c)
    return _build_out(c)


@router.delete("/{cid}", status_code=204)
def desativar(cid: int, db: Session = Depends(get_db)):
    c = db.get(Construtora, cid)
    if not c:
        raise HTTPException(404, "Construtora não encontrada")
    c.ativo = False
    db.commit()
