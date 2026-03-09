from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Analista, Cliente, ComissaoLancamento
from app.schemas import ComissaoAnalista, ComissoesOut, LancamentoCreate, LancamentoOut

router = APIRouter(prefix="/api/comissoes", tags=["Comissoes"])
router.dependencies.append(Depends(get_current_user))


@router.get("", response_model=ComissoesOut)
def get_comissoes(
    ano: int = Query(default=None, description="Ano de referência (padrão: ano atual)"),
    mes: int = Query(default=None, ge=1, le=12, description="Mês de referência (padrão: mês atual)"),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    ano = ano or hoje.year
    mes = mes or hoje.month

    mes_referencia = f"{ano:04d}-{mes:02d}"

    analistas = db.query(Analista).filter(Analista.ativo == True).all()

    resultado: list[ComissaoAnalista] = []
    total_assinaturas = 0
    total_comissoes = Decimal("0.00")

    for analista in analistas:
        # Contratos assinados no mês/ano de referência
        casas = (
            db.query(Cliente)
            .filter(
                Cliente.analista_id == analista.id,
                Cliente.data_assinatura.isnot(None),
                # extrai ano e mês da data_assinatura via comparação de intervalo
                Cliente.data_assinatura >= date(ano, mes, 1),
                Cliente.data_assinatura < (
                    date(ano, mes + 1, 1) if mes < 12 else date(ano + 1, 1, 1)
                ),
            )
            .count()
        )

        comissao_unit = analista.comissao_por_casa or Decimal("80.00")
        meta = analista.meta_mensal or 20
        valor_acumulado = comissao_unit * casas

        if casas == 0:
            pct = 0.0
            status_meta = "abaixo"
        else:
            pct = round((casas / meta) * 100, 1)
            if casas >= meta:
                status_meta = "superou" if casas > meta else "ok"
            else:
                status_meta = "abaixo"

        total_assinaturas += casas
        total_comissoes += valor_acumulado

        resultado.append(ComissaoAnalista(
            analista_id=analista.id,
            nome=analista.nome,
            meta_mensal=meta,
            comissao_por_casa=comissao_unit,
            casas_assinadas_mes=casas,
            valor_acumulado=valor_acumulado,
            percentual_meta=pct,
            status_meta=status_meta,
        ))

    # ordena por mais casas assinadas
    resultado.sort(key=lambda x: x.casas_assinadas_mes, reverse=True)

    return ComissoesOut(
        mes_referencia=mes_referencia,
        analistas=resultado,
        total_assinaturas_mes=total_assinaturas,
        total_comissoes=total_comissoes,
    )


# ── Lançamentos manuais ────────────────────────────────────────────

def _to_lancamento_out(l: ComissaoLancamento) -> LancamentoOut:
    return LancamentoOut(
        id=l.id,
        analista_id=l.analista_id,
        analista_nome=l.analista.nome,
        descricao=l.descricao,
        valor=l.valor,
        data_ref=l.data_ref,
        pago=l.pago,
        data_pagamento=l.data_pagamento,
        created_at=l.created_at,
    )


@router.get("/lancamentos", response_model=list[LancamentoOut])
def listar_lancamentos(
    ano: int = Query(default=None),
    mes: int = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    hoje = date.today()
    ano = ano or hoje.year
    mes = mes or hoje.month
    inicio = date(ano, mes, 1)
    fim = date(ano, mes + 1, 1) if mes < 12 else date(ano + 1, 1, 1)
    rows = (
        db.query(ComissaoLancamento)
        .filter(ComissaoLancamento.data_ref >= inicio, ComissaoLancamento.data_ref < fim)
        .order_by(ComissaoLancamento.created_at.desc())
        .all()
    )
    return [_to_lancamento_out(l) for l in rows]


@router.post("/lancamentos", response_model=LancamentoOut, status_code=201)
def criar_lancamento(payload: LancamentoCreate, db: Session = Depends(get_db)):
    analista = db.get(Analista, payload.analista_id)
    if not analista:
        raise HTTPException(404, "Analista não encontrado")
    l = ComissaoLancamento(**payload.model_dump())
    db.add(l)
    db.commit()
    db.refresh(l)
    return _to_lancamento_out(l)


@router.put("/lancamentos/{lancamento_id}/pagar", response_model=LancamentoOut)
def marcar_pago(lancamento_id: int, db: Session = Depends(get_db)):
    l = db.get(ComissaoLancamento, lancamento_id)
    if not l:
        raise HTTPException(404, "Lançamento não encontrado")
    l.pago = True
    l.data_pagamento = date.today()
    db.commit()
    db.refresh(l)
    return _to_lancamento_out(l)


@router.delete("/lancamentos/{lancamento_id}", status_code=204)
def deletar_lancamento(lancamento_id: int, db: Session = Depends(get_db)):
    l = db.get(ComissaoLancamento, lancamento_id)
    if not l:
        raise HTTPException(404, "Lançamento não encontrado")
    db.delete(l)
    db.commit()
