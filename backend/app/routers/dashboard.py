import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.database import get_db
from app.models import Cliente, Corretor, Analista, Empreendimento, DocStatus, LogAtividade, WorkflowStep
from app.schemas import (
    DashboardOut, KpiDashboard, RankingCorretor, AnalistaCarga, AlertaCartorio,
    FunilStep, RankingCorretorMes, RelatorioEmpItem, RelatorioMensalOut,
    PipelineEtapaItem, PipelineDuracaoOut,
)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])
router.dependencies.append(Depends(get_current_user))

_WF_LABELS = {
    "engenharia":   "Engenharia",
    "aprovacao":    "Aprovação",
    "documentacao": "Certidões",
    "siktd":        "SIKTD",
    "cartorio":      "Cartório",
    "entrega_chave": "Entrega Chave",
    "concluido":    "Concluído",
}


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db)):
    hoje = date.today()
    semana = hoje + timedelta(days=7)
    semana_atras = hoje - timedelta(days=7)

    # ── KPIs ──────────────────────────────────────────────────────
    total_vendas = db.query(func.count(Cliente.id)).filter(Cliente.ativo == True).scalar() or 0

    top = (
        db.query(Corretor.nome, func.count(Cliente.id).label("cnt"))
        .join(Cliente, Cliente.corretor_id == Corretor.id)
        .filter(Cliente.ativo == True)
        .group_by(Corretor.id, Corretor.nome)
        .order_by(func.count(Cliente.id).desc())
        .first()
    )
    top_corretor = top.nome if top else "—"
    top_corretor_vendas = top.cnt if top else 0

    docs_aguardados = (
        db.query(func.count(Cliente.id))
        .filter(
            Cliente.chegada_cartorio.isnot(None),
            Cliente.chegada_cartorio >= hoje,
            Cliente.chegada_cartorio <= semana,
        )
        .scalar() or 0
    )
    docs_recebidos = (
        db.query(func.count(Cliente.id))
        .filter(
            Cliente.doc_recebido == True,
            Cliente.data_doc_recebido >= semana_atras,
        )
        .scalar() or 0
    )
    pendentes = (
        db.query(func.count(Cliente.id))
        .filter(Cliente.ativo == True, Cliente.workflow_step != WorkflowStep.concluido)
        .scalar() or 0
    )
    atrasados = (
        db.query(func.count(Cliente.id))
        .filter(Cliente.ativo == True, Cliente.status == DocStatus.vencido)
        .scalar() or 0
    )

    kpis = KpiDashboard(
        total_vendas=total_vendas,
        top_corretor=top_corretor,
        top_corretor_vendas=top_corretor_vendas,
        docs_aguardados_semana=docs_aguardados,
        docs_recebidos_semana=docs_recebidos,
        processos_pendentes=pendentes,
        processos_atrasados=atrasados,
    )

    # ── Funil do workflow ──────────────────────────────────────────
    funil_rows = (
        db.query(Cliente.workflow_step, func.count(Cliente.id).label("cnt"))
        .filter(Cliente.ativo == True, Cliente.arquivado == False)
        .group_by(Cliente.workflow_step)
        .all()
    )
    step_counts = {r.workflow_step: r.cnt for r in funil_rows}
    funil = [
        FunilStep(step=k, label=v, count=step_counts.get(WorkflowStep(k), 0))
        for k, v in _WF_LABELS.items()
    ]

    # ── Ranking geral corretores ───────────────────────────────────
    ranking_rows = (
        db.query(
            Corretor.id, Corretor.nome,
            func.count(Cliente.id).label("cnt"),
            Empreendimento.nome.label("emp"),
        )
        .join(Cliente, Cliente.corretor_id == Corretor.id)
        .join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)
        .filter(Cliente.ativo == True)
        .group_by(Corretor.id, Corretor.nome, Empreendimento.nome)
        .order_by(func.count(Cliente.id).desc())
        .limit(10)
        .all()
    )
    ranking = [
        RankingCorretor(id=r.id, nome=r.nome, total_vendas=r.cnt, empreendimento_principal=r.emp)
        for r in ranking_rows
    ]

    # ── Ranking semanal (últimos 7 dias) ──────────────────────────
    rank_sem_rows = (
        db.query(
            Corretor.nome,
            func.count(Cliente.id).label("cnt"),
            Empreendimento.nome.label("emp"),
        )
        .join(Cliente, Cliente.corretor_id == Corretor.id)
        .join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)
        .filter(
            Cliente.ativo == True,
            Cliente.data_assinatura.isnot(None),
            Cliente.data_assinatura >= semana_atras,
        )
        .group_by(Corretor.nome, Empreendimento.nome)
        .order_by(func.count(Cliente.id).desc())
        .limit(10)
        .all()
    )
    ranking_semanal = [
        RankingCorretorMes(nome=r.nome, total=r.cnt, empreendimento_principal=r.emp)
        for r in rank_sem_rows
    ]

    # ── Carga analistas ───────────────────────────────────────────
    carga = []
    for analista in db.query(Analista).filter(Analista.ativo == True).all():
        clientes = db.query(Cliente).filter(Cliente.analista_id == analista.id, Cliente.ativo == True).all()
        total = len(clientes)
        concluidos = sum(1 for c in clientes if c.workflow_step == WorkflowStep.concluido)
        atrasados_a = sum(1 for c in clientes if c.status == DocStatus.vencido)
        pendentes_a = total - concluidos - atrasados_a
        carga.append(AnalistaCarga(
            id=analista.id, nome=analista.nome,
            total=total, concluidos=concluidos,
            pendentes=max(pendentes_a, 0), atrasados=atrasados_a,
        ))

    # ── Alertas cartório ──────────────────────────────────────────
    limite_25d = hoje - timedelta(days=25)
    alertas_rows = (
        db.query(Cliente)
        .filter(
            Cliente.doc_recebido == False,
            Cliente.ativo == True,
            (
                (Cliente.chegada_cartorio.isnot(None) & (Cliente.chegada_cartorio <= semana))
                | (Cliente.data_cartorio_envio.isnot(None) & (Cliente.data_cartorio_envio <= limite_25d))
            ),
        )
        .order_by(Cliente.chegada_cartorio.asc())
        .limit(12)
        .all()
    )
    alertas = [
        AlertaCartorio(
            cliente_id=c.id, nome=c.nome,
            empreendimento=c.empreendimento.nome if c.empreendimento else "—",
            chegada_cartorio=c.chegada_cartorio,
            dias_cartorio=(hoje - c.data_cartorio_envio).days if c.data_cartorio_envio else None,
            doc_recebido=c.doc_recebido,
            status="atrasado_25d" if (
                c.data_cartorio_envio and (hoje - c.data_cartorio_envio).days > 25
            ) else (
                "atrasado" if c.chegada_cartorio and c.chegada_cartorio < hoje else "aguardando"
            ),
        )
        for c in alertas_rows
    ]

    return DashboardOut(
        kpis=kpis,
        ranking_corretores=ranking,
        carga_analistas=carga,
        alertas_cartorio=alertas,
        funil_workflow=funil,
        ranking_semanal=ranking_semanal,
    )


# ── Relatório Mensal ──────────────────────────────────────────────
@router.get("/relatorio-mensal", response_model=RelatorioMensalOut)
def relatorio_mensal(
    mes: Optional[str] = Query(None, description="Formato YYYY-MM"),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    if mes:
        try:
            ano, m = int(mes.split("-")[0]), int(mes.split("-")[1])
        except Exception:
            ano, m = hoje.year, hoje.month
    else:
        ano, m = hoje.year, hoje.month

    inicio = date(ano, m, 1)
    fim = date(ano + 1, 1, 1) if m == 12 else date(ano, m + 1, 1)

    empreendimentos = db.query(Empreendimento).filter(Empreendimento.ativo == True).all()
    por_emp = []
    for emp in empreendimentos:
        clientes = (
            db.query(Cliente)
            .filter(Cliente.empreendimento_id == emp.id, Cliente.ativo == True)
            .all()
        )
        if not clientes:
            continue

        total_ativos = sum(1 for c in clientes if not c.arquivado)
        ass_mes = [c for c in clientes if c.data_assinatura and inicio <= c.data_assinatura < fim]
        assinaturas_mes = len(ass_mes)
        rcpm_mes = Decimal(str(sum(float(c.valor_rcpm or 0) for c in ass_mes)))
        concluidos = sum(1 for c in clientes if c.workflow_step == WorkflowStep.concluido)
        em_cartorio = sum(1 for c in clientes if c.workflow_step == WorkflowStep.cartorio)
        atr = sum(1 for c in clientes if c.status == DocStatus.vencido)

        por_emp.append(RelatorioEmpItem(
            empreendimento=emp.nome,
            total_ativos=total_ativos,
            assinaturas_mes=assinaturas_mes,
            rcpm_mes=rcpm_mes,
            concluidos=concluidos,
            em_cartorio=em_cartorio,
            atrasados=atr,
        ))

    por_emp.sort(key=lambda x: x.assinaturas_mes, reverse=True)

    # Ranking corretores do mês
    rank_rows = (
        db.query(
            Corretor.nome,
            func.count(Cliente.id).label("cnt"),
            Empreendimento.nome.label("emp"),
        )
        .join(Cliente, Cliente.corretor_id == Corretor.id)
        .join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)
        .filter(
            Cliente.ativo == True,
            Cliente.data_assinatura >= inicio,
            Cliente.data_assinatura < fim,
        )
        .group_by(Corretor.nome, Empreendimento.nome)
        .order_by(func.count(Cliente.id).desc())
        .limit(15)
        .all()
    )
    ranking = [
        RankingCorretorMes(nome=r.nome, total=r.cnt, empreendimento_principal=r.emp)
        for r in rank_rows
    ]

    total_ass  = sum(e.assinaturas_mes for e in por_emp)
    total_rcpm = sum(e.rcpm_mes for e in por_emp)
    total_conc = sum(e.concluidos for e in por_emp)

    return RelatorioMensalOut(
        mes_referencia=f"{ano:04d}-{m:02d}",
        total_assinaturas=total_ass,
        total_rcpm=total_rcpm,
        total_concluidos=total_conc,
        por_empreendimento=por_emp,
        ranking_corretores=ranking,
    )


# ── Relatório Semanal ─────────────────────────────────────────────
@router.get("/relatorio-semanal", response_model=RelatorioMensalOut)
def relatorio_semanal(
    semana: Optional[str] = Query(None, description="Formato YYYY-Wnn, ex: 2026-W10"),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    if semana:
        try:
            ano_str, w_str = semana.split("-W")
            dt = datetime.strptime(f"{ano_str}-W{int(w_str):02d}-1", "%G-W%V-%u")
            inicio = dt.date()
        except Exception:
            inicio = hoje - timedelta(days=hoje.weekday())  # segunda-feira atual
    else:
        inicio = hoje - timedelta(days=hoje.weekday())  # segunda-feira atual
    fim = inicio + timedelta(days=7)

    empreendimentos = db.query(Empreendimento).filter(Empreendimento.ativo == True).all()
    por_emp = []
    for emp in empreendimentos:
        clientes = (
            db.query(Cliente)
            .filter(Cliente.empreendimento_id == emp.id, Cliente.ativo == True)
            .all()
        )
        if not clientes:
            continue
        total_ativos  = sum(1 for c in clientes if not c.arquivado)
        ass_sem       = [c for c in clientes if c.data_assinatura and inicio <= c.data_assinatura < fim]
        assinaturas   = len(ass_sem)
        rcpm_sem      = Decimal(str(sum(float(c.valor_rcpm or 0) for c in ass_sem)))
        concluidos    = sum(1 for c in clientes if c.workflow_step == WorkflowStep.concluido)
        em_cartorio   = sum(1 for c in clientes if c.workflow_step == WorkflowStep.cartorio)
        atr           = sum(1 for c in clientes if c.status == DocStatus.vencido)
        if not total_ativos:
            continue
        por_emp.append(RelatorioEmpItem(
            empreendimento=emp.nome,
            total_ativos=total_ativos,
            assinaturas_mes=assinaturas,
            rcpm_mes=rcpm_sem,
            concluidos=concluidos,
            em_cartorio=em_cartorio,
            atrasados=atr,
        ))
    por_emp.sort(key=lambda x: x.assinaturas_mes, reverse=True)

    rank_rows = (
        db.query(
            Corretor.nome,
            func.count(Cliente.id).label("cnt"),
            Empreendimento.nome.label("emp"),
        )
        .join(Cliente, Cliente.corretor_id == Corretor.id)
        .join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)
        .filter(
            Cliente.ativo == True,
            Cliente.data_assinatura >= inicio,
            Cliente.data_assinatura < fim,
        )
        .group_by(Corretor.nome, Empreendimento.nome)
        .order_by(func.count(Cliente.id).desc())
        .limit(15)
        .all()
    )
    ranking = [RankingCorretorMes(nome=r.nome, total=r.cnt, empreendimento_principal=r.emp) for r in rank_rows]
    total_ass  = sum(e.assinaturas_mes for e in por_emp)
    total_rcpm = sum(e.rcpm_mes for e in por_emp)
    total_conc = sum(e.concluidos for e in por_emp)

    # Formata label "Semana dd/MM – dd/MM/AAAA"
    label = f"Semana {inicio.strftime('%d/%m')} – {(fim - timedelta(days=1)).strftime('%d/%m/%Y')}"
    return RelatorioMensalOut(
        mes_referencia=label,
        total_assinaturas=total_ass,
        total_rcpm=total_rcpm,
        total_concluidos=total_conc,
        por_empreendimento=por_emp,
        ranking_corretores=ranking,
    )


# ── Relatório de Performance de Corretores ────────────────────────
@router.get("/relatorio-corretores")
def relatorio_corretores(
    mes: Optional[str] = Query(None, description="YYYY-MM"),
    semana: Optional[str] = Query(None, description="YYYY-Wnn"),
    db: Session = Depends(get_db),
):
    """Performance individual de cada corretor num período (mensal ou semanal)."""
    from sqlalchemy.orm import joinedload

    hoje = date.today()
    if semana:
        try:
            ano_str, w_str = semana.split("-W")
            dt = datetime.strptime(f"{ano_str}-W{int(w_str):02d}-1", "%G-W%V-%u")
            inicio = dt.date()
        except Exception:
            inicio = hoje - timedelta(days=hoje.weekday())
        fim = inicio + timedelta(days=7)
        label = f"Semana {inicio.strftime('%d/%m')} – {(fim - timedelta(days=1)).strftime('%d/%m/%Y')}"
    else:
        if mes:
            try:
                ano, m = int(mes.split("-")[0]), int(mes.split("-")[1])
            except Exception:
                ano, m = hoje.year, hoje.month
        else:
            ano, m = hoje.year, hoje.month
        inicio = date(ano, m, 1)
        fim = date(ano + 1, 1, 1) if m == 12 else date(ano, m + 1, 1)
        label = f"{ano:04d}-{m:02d}"

    corretores = db.query(Corretor).filter(Corretor.ativo == True).order_by(Corretor.nome).all()

    all_clients = (
        db.query(Cliente)
        .options(joinedload(Cliente.empreendimento))
        .filter(Cliente.ativo == True, Cliente.deleted_at == None, Cliente.corretor_id != None)
        .all()
    )

    por_cor: dict = defaultdict(list)
    for c in all_clients:
        por_cor[c.corretor_id].append(c)

    total_ass_periodo = 0
    result = []

    for cor in corretores:
        clientes = por_cor.get(cor.id, [])
        ass_periodo = [
            c for c in clientes
            if c.data_assinatura and inicio <= c.data_assinatura < fim
        ]
        total = len(clientes)
        concluidos = sum(1 for c in clientes if c.workflow_step and c.workflow_step.value == "concluido")
        emps_set: dict[str, int] = {}
        for c in clientes:
            n = c.empreendimento.nome if c.empreendimento else "—"
            emps_set[n] = emps_set.get(n, 0) + 1
        emps = [{"nome": k, "total": v} for k, v in sorted(emps_set.items(), key=lambda x: -x[1])]

        assinaturas = len(ass_periodo)
        total_ass_periodo += assinaturas

        result.append({
            "id": cor.id,
            "nome": cor.nome,
            "creci": cor.creci or "",
            "telefone": cor.telefone or "",
            "assinaturas_periodo": assinaturas,
            "total_clientes": total,
            "concluidos": concluidos,
            "em_andamento": total - concluidos,
            "empreendimentos": emps,
            "pct_do_total": 0,
        })

    result.sort(key=lambda x: (-x["assinaturas_periodo"], -x["total_clientes"]))

    for r in result:
        r["pct_do_total"] = (
            round(r["assinaturas_periodo"] / total_ass_periodo * 100, 1)
            if total_ass_periodo else 0
        )

    return {
        "periodo": label,
        "total_corretores": len(corretores),
        "total_assinaturas_periodo": total_ass_periodo,
        "corretores": result,
    }


# ── Pipeline — Duração por Etapa ──────────────────────────────────
_WF_ORDER_LIST = [
    "engenharia", "aprovacao", "documentacao",
    "siktd", "cartorio", "entrega_chave", "concluido",
]

@router.get("/pipeline-duracao", response_model=PipelineDuracaoOut)
def pipeline_duracao(db: Session = Depends(get_db)):
    # Mapa cliente_id → created_at
    clientes_map: dict[int, datetime] = {
        c.id: c.created_at
        for c in db.query(Cliente.id, Cliente.created_at).filter(Cliente.ativo == True).all()
    }

    # Todos os logs de mudança de workflow, ordenados por cliente e tempo
    logs = (
        db.query(LogAtividade)
        .filter(LogAtividade.acao == "workflow_alterado")
        .order_by(LogAtividade.cliente_id, LogAtividade.created_at)
        .all()
    )

    # Agrupa por cliente
    client_logs: dict[int, list] = defaultdict(list)
    for log in logs:
        client_logs[log.cliente_id].append(log)

    step_days: dict[str, list[float]] = defaultdict(list)
    _pat = re.compile(r"^(\w+)\s*→\s*(\w+)")

    for cliente_id, clogs in client_logs.items():
        prev_time = clientes_map.get(cliente_id)
        if prev_time is None:
            continue
        for log in clogs:
            m = _pat.match(log.detalhes or "")
            if not m:
                continue
            from_step = m.group(1)
            days = (log.created_at - prev_time).total_seconds() / 86400
            if 0 <= days <= 730:  # sanity: até 2 anos
                step_days[from_step].append(days)
            prev_time = log.created_at

    etapas = []
    for step in _WF_ORDER_LIST:
        vals = step_days.get(step, [])
        if not vals:
            etapas.append(PipelineEtapaItem(
                step=step,
                label=_WF_LABELS.get(step, step),
                processos=0,
                media_dias=0.0,
                min_dias=0,
                max_dias=0,
            ))
            continue
        etapas.append(PipelineEtapaItem(
            step=step,
            label=_WF_LABELS.get(step, step),
            processos=len(vals),
            media_dias=round(sum(vals) / len(vals), 1),
            min_dias=int(min(vals)),
            max_dias=int(max(vals)),
        ))

    return PipelineDuracaoOut(
        total_processos=len(clientes_map),
        etapas=etapas,
    )
