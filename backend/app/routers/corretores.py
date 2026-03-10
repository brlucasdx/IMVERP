from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from app.auth import get_current_user
from app.database import get_db
from app.models import Corretor, Cliente, Empreendimento, WorkflowStep
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


_WF_LABELS = {
    "engenharia":    "Engenharia",
    "aprovacao":     "Aprovação",
    "documentacao":  "Documentação",
    "siktd":         "SIKTD",
    "cartorio":      "Cartório",
    "entrega_chave": "Entrega Chave",
    "concluido":     "Concluído",
}


@router.get("/{corretor_id}/kpi")
def kpi_corretor(corretor_id: int, db: Session = Depends(get_db)) -> Any:
    """KPIs detalhados de um corretor: clientes, breakdown por empreendimento e por etapa."""
    corretor = db.get(Corretor, corretor_id)
    if not corretor or not corretor.ativo:
        raise HTTPException(404, "Corretor não encontrado")

    clientes = (
        db.query(Cliente)
        .filter(
            Cliente.corretor_id == corretor_id,
            Cliente.ativo == True,
            Cliente.deleted_at == None,
        )
        .order_by(Cliente.nome)
        .all()
    )

    # Breakdown por empreendimento
    emp_counts: dict[str, int] = {}
    for c in clientes:
        nome_emp = c.empreendimento.nome if c.empreendimento else "Sem empreendimento"
        emp_counts[nome_emp] = emp_counts.get(nome_emp, 0) + 1

    por_empreendimento = [
        {"empreendimento": k, "total": v}
        for k, v in sorted(emp_counts.items(), key=lambda x: -x[1])
    ]

    # Breakdown por etapa
    step_counts: dict[str, int] = {}
    for c in clientes:
        step = c.workflow_step.value if c.workflow_step else "engenharia"
        step_counts[step] = step_counts.get(step, 0) + 1

    por_etapa = [
        {"step": k, "label": _WF_LABELS.get(k, k), "total": v}
        for k, v in step_counts.items()
    ]

    # Lista de clientes
    lista_clientes = [
        {
            "id": c.id,
            "nome": c.nome,
            "num_ordem": c.num_ordem,
            "empreendimento": c.empreendimento.nome if c.empreendimento else "—",
            "workflow_step": c.workflow_step.value if c.workflow_step else "engenharia",
            "workflow_label": _WF_LABELS.get(
                c.workflow_step.value if c.workflow_step else "engenharia", ""
            ),
            "arquivado": c.arquivado,
        }
        for c in clientes
    ]

    return {
        "corretor": {
            "id": corretor.id,
            "nome": corretor.nome,
            "creci": corretor.creci,
            "telefone": corretor.telefone,
        },
        "total_clientes": len(clientes),
        "por_empreendimento": por_empreendimento,
        "por_etapa": por_etapa,
        "clientes": lista_clientes,
    }
