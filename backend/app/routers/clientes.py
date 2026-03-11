import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db, settings
from app.models import Cliente, ClientePdf, DocStatus, Empreendimento, LogAtividade, Nota, Usuario, WorkflowStep
from app.schemas import ClienteCreate, ClienteOut, ClienteUpdate, ClientePdfOut, LogOut, NotaCreate, NotaOut

router = APIRouter(prefix="/api/clientes", tags=["Clientes"])
router.dependencies.append(Depends(get_current_user))

ALLOWED_EXTENSIONS = {".pdf"}

# Nomes amigáveis dos campos para log
_CAMPO_LABEL = {
    "nome": "Nome", "telefone": "Telefone", "logradouro": "Logradouro",
    "quadra": "Quadra", "lote": "Lote", "analista_id": "Analista",
    "corretor_id": "Corretor", "data_assinatura": "Data assinatura",
    "data_siktd_ok": "Data SIKTD", "data_cartorio_envio": "Envio cartório",
    "chegada_cartorio": "Chegada cartório", "valor_rcpm": "Seg. RCPM",
    "valor_avaliacao": "Avaliação", "valor_venda": "Valor venda",
    "observacoes": "Observações",
}


def _recalc_status(cliente: Cliente) -> DocStatus:
    if cliente.doc_recebido:
        return DocStatus.ok
    if cliente.chegada_cartorio and cliente.chegada_cartorio < date.today():
        return DocStatus.vencido
    return DocStatus.proximo


def _log(db: Session, cliente_id: int, acao: str, detalhes: str = None, usuario_id: int = None):
    """Registra uma ação no histórico do cliente. NÃO faz commit — deve ser feito pelo caller."""
    db.add(LogAtividade(
        cliente_id=cliente_id,
        acao=acao,
        detalhes=detalhes,
        usuario_id=usuario_id,
    ))


# ── Listar ────────────────────────────────────────────────────────
@router.get("", response_model=list[ClienteOut])
def listar_clientes(
    busca: Optional[str] = Query(None, description="Nome, CPF ou casa"),
    empreendimento_id: Optional[int] = None,
    analista_id: Optional[int] = None,
    unidade_id: Optional[int] = None,
    status: Optional[DocStatus] = None,
    arquivados: Optional[bool] = False,   # False = Processos | True = Base
    db: Session = Depends(get_db),
):
    q = db.query(Cliente).filter(Cliente.ativo == True)

    if arquivados:
        q = q.filter(Cliente.arquivado == True)
    else:
        q = q.filter(Cliente.arquivado == False)

    if busca:
        term = f"%{busca}%"
        q = q.filter(
            Cliente.nome.ilike(term)
            | Cliente.cpf.ilike(term)
            | Cliente.casa_num.ilike(term)
            | Cliente.logradouro.ilike(term)
        )
    if empreendimento_id:
        q = q.filter(Cliente.empreendimento_id == empreendimento_id)
    if analista_id:
        q = q.filter(Cliente.analista_id == analista_id)
    if unidade_id:
        q = q.join(Empreendimento, Cliente.empreendimento_id == Empreendimento.id)\
             .filter(Empreendimento.unidade_id == unidade_id)
    if status:
        q = q.filter(Cliente.status == status)

    order = Cliente.arquivado_em.desc() if arquivados else Cliente.num_ordem
    return q.order_by(order).all()


# ── Criar ─────────────────────────────────────────────────────────
@router.post("", response_model=ClienteOut, status_code=201)
def criar_cliente(
    payload: ClienteCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    if db.query(Cliente).filter(Cliente.cpf == payload.cpf).first():
        raise HTTPException(400, "CPF já cadastrado")

    # Auto-gerar num_ordem no formato YYMM.N (ex: 2603.1)
    hoje = date.today()
    prefixo = f"{str(hoje.year)[2:]}{hoje.month:02d}"
    count = db.query(Cliente).filter(Cliente.num_ordem.like(f"{prefixo}.%")).count()
    num_ordem = f"{prefixo}.{count + 1}"

    data = payload.model_dump()
    data["num_ordem"] = num_ordem
    cliente = Cliente(**data)
    cliente.status = _recalc_status(cliente)
    db.add(cliente)
    db.flush()  # gera cliente.id antes do commit

    _log(db, cliente.id, "cliente_criado",
         f"Processo cadastrado por {current_user.nome}",
         current_user.id)

    db.commit()
    db.refresh(cliente)
    return cliente


# ── Lixeira (ADM) ────────────────────────────────────────────────
@router.get("/lixeira", response_model=list[ClienteOut])
def lixeira(db: Session = Depends(get_db), _: Usuario = Depends(require_admin)):
    return (
        db.query(Cliente)
        .filter(Cliente.ativo == False)
        .order_by(Cliente.deleted_at.desc())
        .all()
    )


# ── Arquivar (mover para Base) ────────────────────────────────────
@router.post("/{cliente_id}/arquivar", response_model=ClienteOut)
def arquivar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(404, "Cliente não encontrado")
    if cliente.workflow_step.value != "concluido":
        raise HTTPException(400, "Somente processos concluídos podem ser arquivados")
    if not cliente.chave_liberada:
        raise HTTPException(400, "A chave do cliente ainda não foi entregue. Conclua a etapa de entrega antes de arquivar.")
    cliente.arquivado    = True
    cliente.arquivado_em = datetime.utcnow()
    _log(db, cliente_id, "arquivado",
         f"Processo arquivado na Base por {current_user.nome}",
         current_user.id)
    db.commit()
    db.refresh(cliente)
    return cliente


# ── Desarquivar (voltar para Processos) ───────────────────────────
@router.post("/{cliente_id}/desarquivar", response_model=ClienteOut)
def desarquivar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(404, "Cliente não encontrado")
    cliente.arquivado    = False
    cliente.arquivado_em = None
    _log(db, cliente_id, "desarquivado",
         f"Processo devolvido para Processos por {current_user.nome}",
         current_user.id)
    db.commit()
    db.refresh(cliente)
    return cliente


# ── Restaurar (ADM) ───────────────────────────────────────────────
@router.post("/{cliente_id}/restaurar", response_model=ClienteOut)
def restaurar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    if cliente.ativo:
        raise HTTPException(400, "Cliente já está ativo")
    cliente.ativo = True
    cliente.deleted_at = None
    _log(db, cliente_id, "restaurado",
         f"Processo restaurado da lixeira por {current_user.nome}",
         current_user.id)
    db.commit()
    db.refresh(cliente)
    return cliente


# ── Buscar um ─────────────────────────────────────────────────────
@router.get("/{cliente_id}", response_model=ClienteOut)
def buscar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(404, "Cliente não encontrado")
    return cliente


# ── Atualizar ─────────────────────────────────────────────────────
@router.put("/{cliente_id}", response_model=ClienteOut)
def atualizar_cliente(
    cliente_id: int,
    payload: ClienteUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    # Captura estado anterior
    wf_antes    = cliente.workflow_step
    doc_antes   = cliente.doc_recebido
    chave_antes = cliente.chave_liberada

    changes = payload.model_dump(exclude_none=True)

    # Detecta quais campos realmente mudaram (compara antes de aplicar)
    campos_alterados = []
    for campo, novo_valor in changes.items():
        valor_atual = getattr(cliente, campo, None)
        # Normaliza para comparação: enum → valor, Decimal → str
        va = valor_atual.value if hasattr(valor_atual, "value") else valor_atual
        nv = novo_valor.value  if hasattr(novo_valor,  "value") else novo_valor
        if va != nv:
            campos_alterados.append(campo)

    for campo, valor in changes.items():
        setattr(cliente, campo, valor)

    if payload.doc_recebido and not doc_antes:
        cliente.data_doc_recebido = date.today()

    cliente.status = _recalc_status(cliente)

    uid = current_user.id

    # Log específico: workflow
    if "workflow_step" in campos_alterados:
        _log(db, cliente_id, "workflow_alterado",
             f"{wf_antes.value} → {cliente.workflow_step.value}",
             uid)

    # Log específico: documento recebido
    if "doc_recebido" in campos_alterados and cliente.doc_recebido:
        _log(db, cliente_id, "doc_recebido",
             "Documento de garantia marcado como recebido",
             uid)

    # Log específico: chave liberada
    if "chave_liberada" in campos_alterados and cliente.chave_liberada:
        _log(db, cliente_id, "chave_liberada",
             "Chave física entregue ao cliente",
             uid)

    # Log genérico para outros campos alterados
    _skip = {"workflow_step", "doc_recebido", "chave_liberada", "status",
             "data_doc_recebido", "data_chave_liberada"}
    outros = [k for k in campos_alterados if k not in _skip]
    if outros:
        campos_str = ", ".join(_CAMPO_LABEL.get(k, k) for k in outros)
        _log(db, cliente_id, "dados_atualizados",
             f"Campos alterados: {campos_str}",
             uid)

    db.commit()
    db.refresh(cliente)
    return cliente


# ── Deletar (soft) ────────────────────────────────────────────────
@router.delete("/{cliente_id}", status_code=204)
def deletar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(404, "Cliente não encontrado")
    cliente.ativo = False
    cliente.deleted_at = datetime.utcnow()
    _log(db, cliente_id, "deletado",
         f"Processo movido para a lixeira por {current_user.nome}",
         current_user.id)
    db.commit()


# ── Upload PDF ────────────────────────────────────────────────────
MAX_PDF_SIZE = 5 * 1024 * 1024   # 5 MB por arquivo

@router.post("/{cliente_id}/upload", response_model=ClientePdfOut)
async def upload_pdf(
    cliente_id: int,
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    ext = Path(arquivo.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Somente arquivos PDF são aceitos")

    data = await arquivo.read()
    if len(data) > MAX_PDF_SIZE:
        raise HTTPException(400, "Arquivo muito grande — máximo 5 MB")

    pdf = ClientePdf(
        cliente_id=cliente_id,
        filename=arquivo.filename,
        data=data,
        tamanho=len(data),
    )
    db.add(pdf)
    # mantém pdf_path como indicador de presença (usado em RCPM etc.)
    cliente.pdf_path = arquivo.filename
    _log(db, cliente_id, "pdf_enviado",
         f"{arquivo.filename} enviado por {current_user.nome}",
         current_user.id)
    db.commit()
    db.refresh(pdf)
    return pdf


# ── Listar PDFs do cliente ─────────────────────────────────────────
@router.get("/{cliente_id}/pdfs", response_model=list[ClientePdfOut])
def listar_pdfs(
    cliente_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return db.query(ClientePdf).filter(ClientePdf.cliente_id == cliente_id).order_by(ClientePdf.created_at.desc()).all()


# ── Download PDF por ID ────────────────────────────────────────────
@router.get("/pdfs/{pdf_id}/download")
def download_pdf(
    pdf_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    pdf = db.get(ClientePdf, pdf_id)
    if not pdf:
        raise HTTPException(404, "PDF não encontrado")
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in pdf.filename)
    return Response(
        content=pdf.data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


# ── Excluir PDF ────────────────────────────────────────────────────
@router.delete("/pdfs/{pdf_id}")
def excluir_pdf(
    pdf_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    pdf = db.get(ClientePdf, pdf_id)
    if not pdf:
        raise HTTPException(404, "PDF não encontrado")
    cliente_id = pdf.cliente_id
    filename = pdf.filename
    db.delete(pdf)
    # atualiza pdf_path: se ainda houver PDFs, mantém o mais recente; senão limpa
    restantes = db.query(ClientePdf).filter(ClientePdf.cliente_id == cliente_id).order_by(ClientePdf.created_at.desc()).first()
    cliente = db.get(Cliente, cliente_id)
    if cliente:
        cliente.pdf_path = restantes.filename if restantes else None
    _log(db, cliente_id, "pdf_excluido",
         f"{filename} excluído por {current_user.nome}",
         current_user.id)
    db.commit()
    return {"ok": True}


# ── Logs do cliente ───────────────────────────────────────────────
@router.get("/{cliente_id}/logs", response_model=list[LogOut])
def listar_logs(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return (
        db.query(LogAtividade)
        .filter(LogAtividade.cliente_id == cliente_id)
        .order_by(LogAtividade.created_at.desc())
        .all()
    )


# ── Notas do cliente ──────────────────────────────────────────────
@router.get("/{cliente_id}/notas", response_model=list[NotaOut])
def listar_notas(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.get(Cliente, cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return (
        db.query(Nota)
        .filter(Nota.cliente_id == cliente_id)
        .order_by(Nota.created_at.desc())
        .all()
    )


@router.post("/{cliente_id}/notas", response_model=NotaOut, status_code=201)
def criar_nota(
    cliente_id: int,
    payload: NotaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    cliente = db.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(404, "Cliente não encontrado")
    if not payload.texto.strip():
        raise HTTPException(400, "Nota não pode ser vazia")

    nota = Nota(cliente_id=cliente_id, usuario_id=current_user.id, texto=payload.texto.strip())
    db.add(nota)
    txt_preview = payload.texto.strip()[:120]
    if len(payload.texto.strip()) > 120:
        txt_preview += "…"
    _log(db, cliente_id, "nota_adicionada",
         f"{current_user.nome}: \"{txt_preview}\"",
         current_user.id)
    db.commit()
    db.refresh(nota)
    return nota


@router.delete("/notas/{nota_id}", status_code=204)
def deletar_nota(
    nota_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    nota = db.get(Nota, nota_id)
    if not nota:
        raise HTTPException(404, "Nota não encontrada")
    # Somente o autor ou admin pode deletar
    from app.models import TipoUsuario
    if nota.usuario_id != current_user.id and current_user.tipo != TipoUsuario.admin:
        raise HTTPException(403, "Sem permissão para excluir esta nota")
    db.delete(nota)
    db.commit()
