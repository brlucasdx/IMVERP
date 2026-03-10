from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.database import get_db
from app.models import Cliente, Empreendimento, DocStatus, WorkflowStep

router = APIRouter(prefix="/api/rcpm", tags=["RCPM"])
router.dependencies.append(Depends(get_current_user))


@router.get("/conciliacao")
def conciliacao(db: Session = Depends(get_db)):
    """
    Agrupa por empreendimento o total de apólices RCPM e o valor acumulado.
    Retorna apenas empreendimentos com ao menos um cliente com valor_rcpm preenchido.
    """
    empreendimentos = db.query(Empreendimento).filter(Empreendimento.ativo == True).all()
    result = []
    total_geral = Decimal("0")

    for emp in empreendimentos:
        rows = (
            db.query(func.count(Cliente.id), func.sum(Cliente.valor_rcpm))
            .filter(
                Cliente.empreendimento_id == emp.id,
                Cliente.ativo == True,
                Cliente.valor_rcpm.isnot(None),
            )
            .first()
        )
        total_apolices = rows[0] or 0
        if total_apolices == 0:
            continue

        valor_total = (rows[1] or Decimal("0")).quantize(Decimal("0.01"))
        total_geral += valor_total

        # Quantos processos estão em cartório ou com doc atrasado
        atrasados = (
            db.query(func.count(Cliente.id))
            .filter(
                Cliente.empreendimento_id == emp.id,
                Cliente.ativo == True,
                Cliente.status == DocStatus.vencido,
            )
            .scalar() or 0
        )
        em_cartorio = (
            db.query(func.count(Cliente.id))
            .filter(
                Cliente.empreendimento_id == emp.id,
                Cliente.ativo == True,
                Cliente.workflow_step == WorkflowStep.cartorio,
            )
            .scalar() or 0
        )

        result.append({
            "empreendimento_id": emp.id,
            "empreendimento": emp.nome,
            "construtora": emp.construtora or "—",
            "total_apolices": total_apolices,
            "valor_total_rcpm": float(valor_total),
            "em_cartorio": em_cartorio,
            "atrasados": atrasados,
        })

    result.sort(key=lambda x: x["valor_total_rcpm"], reverse=True)
    return {
        "total_geral_rcpm": float(total_geral),
        "total_apolices": sum(r["total_apolices"] for r in result),
        "por_empreendimento": result,
    }


@router.get("/em-cartorio")
def em_cartorio(db: Session = Depends(get_db)):
    """
    Lista todos os clientes atualmente na etapa de cartório,
    ordenados pelo tempo em cartório (mais antigos primeiro).
    """
    hoje = date.today()
    clientes = (
        db.query(Cliente)
        .options(joinedload(Cliente.empreendimento))
        .filter(
            Cliente.ativo == True,
            Cliente.deleted_at == None,
            Cliente.workflow_step == WorkflowStep.cartorio,
        )
        .order_by(Cliente.chegada_cartorio.asc().nullslast())
        .all()
    )

    result = []
    for c in clientes:
        if c.chegada_cartorio:
            dias = (hoje - c.chegada_cartorio).days
            urgencia = "critico" if dias > 30 else "alerta" if dias > 15 else "normal"
        else:
            dias = None
            urgencia = "sem-data"

        result.append({
            "id": c.id,
            "num_ordem": c.num_ordem,
            "nome": c.nome,
            "empreendimento": c.empreendimento.nome if c.empreendimento else "—",
            "empreendimento_id": c.empreendimento_id,
            "construtora": c.empreendimento.construtora if c.empreendimento else "—",
            "casa": c.casa_num,
            "chegada_cartorio": str(c.chegada_cartorio) if c.chegada_cartorio else None,
            "dias_em_cartorio": dias,
            "urgencia": urgencia,
            "valor_rcpm": float(c.valor_rcpm) if c.valor_rcpm else None,
            "doc_recebido": c.doc_recebido,
        })

    return {
        "total": len(result),
        "criticos": sum(1 for r in result if r["urgencia"] == "critico"),
        "clientes": result,
    }


@router.get("/vencimentos")
def vencimentos(
    status: Optional[str] = Query(None),         # ok | proximo | vencido
    empreendimento_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Lista clientes com chegada_cartorio preenchida, ordenados pela data.
    Inclui situação atual de cada um.
    """
    hoje = date.today()
    q = (
        db.query(Cliente)
        .filter(
            Cliente.ativo == True,
            Cliente.chegada_cartorio.isnot(None),
        )
        .order_by(Cliente.chegada_cartorio.asc())
    )
    if status:
        q = q.filter(Cliente.status == DocStatus(status))
    if empreendimento_id:
        q = q.filter(Cliente.empreendimento_id == empreendimento_id)

    result = []
    for c in q.all():
        dias = (c.chegada_cartorio - hoje).days
        if c.doc_recebido:
            situacao = "recebido"
            situacao_label = "✓ Recebido"
        elif dias < 0:
            situacao = "atrasado"
            situacao_label = f"⚠ Atrasado há {abs(dias)} dias"
        elif dias <= 7:
            situacao = "proximo"
            situacao_label = f"⏳ Vence em {dias} dia{'s' if dias != 1 else ''}"
        else:
            situacao = "ok"
            situacao_label = f"📅 Previsto em {dias} dias"

        result.append({
            "id": c.id,
            "num_ordem": c.num_ordem,
            "nome": c.nome,
            "empreendimento": c.empreendimento.nome if c.empreendimento else "—",
            "empreendimento_id": c.empreendimento_id,
            "casa": c.casa_num,
            "data_assinatura": str(c.data_assinatura) if c.data_assinatura else None,
            "chegada_cartorio": str(c.chegada_cartorio),
            "dias": dias,
            "doc_recebido": c.doc_recebido,
            "data_doc_recebido": str(c.data_doc_recebido) if c.data_doc_recebido else None,
            "valor_rcpm": float(c.valor_rcpm) if c.valor_rcpm else None,
            "situacao": situacao,
            "situacao_label": situacao_label,
            "pdf": bool(c.pdf_path),
            "status": c.status.value,
        })
    return result
