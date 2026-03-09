from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Cliente, Empreendimento, LogAtividade, Usuario, WorkflowStep
from app.schemas import ClienteChave

router = APIRouter(prefix="/api/chaves", tags=["Chaves"])
router.dependencies.append(Depends(get_current_user))

_WF_ORDER = [
    WorkflowStep.engenharia, WorkflowStep.aprovacao, WorkflowStep.documentacao,
    WorkflowStep.siktd, WorkflowStep.cartorio, WorkflowStep.entrega_chave, WorkflowStep.concluido,
]


def _log(db: Session, cliente_id: int, acao: str, detalhes: str = None, usuario_id: int = None):
    db.add(LogAtividade(cliente_id=cliente_id, acao=acao, detalhes=detalhes, usuario_id=usuario_id))


def _status_chave(c: Cliente) -> str:
    if c.chave_liberada:
        return "liberada"
    chave_rapida = c.empreendimento.chave_rapida if c.empreendimento else False
    if chave_rapida or c.doc_recebido:
        return "apto"
    return "aguardando"


def _to_schema(c: Cliente) -> ClienteChave:
    return ClienteChave(
        id=c.id,
        num_ordem=c.num_ordem,
        nome=c.nome,
        empreendimento=c.empreendimento.nome if c.empreendimento else "—",
        casa_num=c.casa_num,
        logradouro=c.logradouro,
        data_assinatura=c.data_assinatura,
        chave_rapida=c.empreendimento.chave_rapida if c.empreendimento else False,
        doc_recebido=c.doc_recebido,
        chave_liberada=c.chave_liberada,
        data_chave_liberada=c.data_chave_liberada,
        status_chave=_status_chave(c),
        workflow_step=c.workflow_step.value,
        corretor=c.corretor.nome if c.corretor else None,
        analista=c.analista.nome if c.analista else None,
    )


@router.get("", response_model=list[ClienteChave])
def listar_chaves(
    apenas_pendentes: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    _LATE_STEPS = [
        WorkflowStep.siktd, WorkflowStep.cartorio,
        WorkflowStep.entrega_chave, WorkflowStep.concluido,
    ]
    clientes = (
        db.query(Cliente)
        .join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)
        .filter(
            Cliente.ativo == True,
            Cliente.arquivado == False,
            or_(
                Cliente.data_assinatura.isnot(None),
                Cliente.workflow_step.in_(_LATE_STEPS),
            ),
        )
        .order_by(Cliente.data_assinatura.desc().nullslast())
        .all()
    )

    resultado = []
    for c in clientes:
        st = _status_chave(c)
        if apenas_pendentes and st == "liberada":
            continue
        resultado.append(_to_schema(c))

    ORDER = {"apto": 0, "aguardando": 1, "liberada": 2}
    resultado.sort(key=lambda x: ORDER[x.status_chave])
    return resultado


@router.post("/{cliente_id}/liberar", response_model=ClienteChave)
def liberar_chave(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    c = db.get(Cliente, cliente_id)
    if not c or not c.ativo:
        raise HTTPException(404, "Cliente não encontrado")

    chave_rapida = c.empreendimento.chave_rapida if c.empreendimento else False
    if not chave_rapida and not c.doc_recebido:
        raise HTTPException(400, "Chave não pode ser liberada: documento do cartório ainda não foi recebido.")
    if c.chave_liberada:
        raise HTTPException(400, "Chave já foi liberada.")

    c.chave_liberada = True
    c.data_chave_liberada = date.today()

    # Avança workflow para entrega_chave se ainda não chegou nessa etapa
    wf_antes = c.workflow_step
    idx_atual  = _WF_ORDER.index(c.workflow_step) if c.workflow_step in _WF_ORDER else 0
    idx_entrega = _WF_ORDER.index(WorkflowStep.entrega_chave)
    if idx_atual < idx_entrega:
        c.workflow_step = WorkflowStep.entrega_chave
        _log(db, cliente_id, "workflow_alterado",
             f"{wf_antes.value} → entrega_chave (automático ao liberar chave)",
             current_user.id)

    _log(db, cliente_id, "chave_liberada",
         f"Chave física entregue ao cliente por {current_user.nome}",
         current_user.id)

    db.commit()
    db.refresh(c)
    return _to_schema(c)


@router.post("/{cliente_id}/concluir", response_model=ClienteChave)
def concluir_processo(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Marca como concluído. Só permitido após a chave ter sido liberada."""
    c = db.get(Cliente, cliente_id)
    if not c or not c.ativo:
        raise HTTPException(404, "Cliente não encontrado")
    if not c.chave_liberada:
        raise HTTPException(400, "Processo não pode ser concluído antes da entrega da chave.")
    if c.workflow_step == WorkflowStep.concluido:
        raise HTTPException(400, "Processo já está concluído.")

    wf_antes = c.workflow_step
    c.workflow_step = WorkflowStep.concluido
    _log(db, cliente_id, "workflow_alterado",
         f"{wf_antes.value} → concluido",
         current_user.id)

    db.commit()
    db.refresh(c)
    return _to_schema(c)
