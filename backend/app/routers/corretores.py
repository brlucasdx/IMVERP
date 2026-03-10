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


@router.get("")
def listar_corretores(db: Session = Depends(get_db)) -> Any:
    corretores = (
        db.query(Corretor)
        .filter(Corretor.ativo == True)
        .order_by(Corretor.nome)
        .all()
    )

    # Uma query só: todos os clientes ativos com corretor, empreendimento e workflow
    from sqlalchemy.orm import joinedload
    clientes_all = (
        db.query(Cliente)
        .options(joinedload(Cliente.empreendimento))
        .filter(Cliente.ativo == True, Cliente.deleted_at == None, Cliente.corretor_id != None)
        .all()
    )

    # Agrupa por corretor_id em Python (evita N+1)
    from collections import defaultdict
    por_cor: dict[int, list] = defaultdict(list)
    for c in clientes_all:
        por_cor[c.corretor_id].append(c)

    result = []
    for cor in corretores:
        clientes = por_cor.get(cor.id, [])
        total = len(clientes)
        concluidos = sum(1 for c in clientes if c.workflow_step and c.workflow_step.value == "concluido")
        # top 3 empreendimentos por quantidade
        emp_cnt: dict[str, int] = {}
        for c in clientes:
            n = c.empreendimento.nome if c.empreendimento else "—"
            emp_cnt[n] = emp_cnt.get(n, 0) + 1
        top_emps = sorted(emp_cnt.items(), key=lambda x: -x[1])[:3]

        result.append({
            "id": cor.id,
            "nome": cor.nome,
            "creci": cor.creci,
            "telefone": cor.telefone,
            "ativo": cor.ativo,
            "total_vendas": total,
            "concluidos": concluidos,
            "em_andamento": total - concluidos,
            "empreendimentos": [{"nome": k, "total": v} for k, v in top_emps],
        })

    # ordena por total desc
    result.sort(key=lambda x: -x["total_vendas"])
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
