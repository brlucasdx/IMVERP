from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class WorkflowStep(str, enum.Enum):
    engenharia    = "engenharia"     # Etapa 1: Laudo do engenheiro
    aprovacao     = "aprovacao"      # Etapa 2: Aprovação de crédito / assinatura Caixa
    documentacao  = "documentacao"   # Etapa 3: Certidões e pesquisas
    siktd         = "siktd"          # Etapa 4: Envio digital sistema Caixa
    cartorio      = "cartorio"       # Etapa 5: Cartório (autenticação física 20-30 dias)
    entrega_chave = "entrega_chave"  # Etapa 6: Entrega da chave ao cliente
    concluido     = "concluido"      # Etapa 7: Processo encerrado


class DocStatus(str, enum.Enum):
    ok      = "ok"       # garantia recebida do cartório
    proximo = "proximo"  # dentro do prazo
    vencido = "vencido"  # atrasado / sem retorno


class Unidade(Base):
    """Filial/escritório. Cada empreendimento pertence a uma unidade."""
    __tablename__ = "unidades"

    id      = Column(Integer, primary_key=True, index=True)
    nome    = Column(String(120), nullable=False)   # ex.: "Manaus", "Santa Maria"
    cidade  = Column(String(120), nullable=False)
    estado  = Column(String(2),   nullable=False)   # UF, ex.: "AM", "RS"
    ativo   = Column(Boolean, default=True)

    empreendimentos = relationship("Empreendimento", back_populates="unidade")


class Construtora(Base):
    """Empresa construtora/incorporadora parceira."""
    __tablename__ = "construtoras"

    id          = Column(Integer, primary_key=True, index=True)
    nome        = Column(String(120), nullable=False, unique=True)
    cnpj        = Column(String(18))          # "00.000.000/0000-00"
    telefone    = Column(String(20))
    email       = Column(String(150))
    responsavel = Column(String(120))         # nome do contato principal
    ativo       = Column(Boolean, default=True)

    empreendimentos = relationship("Empreendimento", back_populates="construtora_rel")


class Empreendimento(Base):
    __tablename__ = "empreendimentos"

    id              = Column(Integer, primary_key=True, index=True)
    nome            = Column(String(120), nullable=False, unique=True)
    construtora     = Column(String(120))    # display name (legacy / fallback)
    construtora_id  = Column(Integer, ForeignKey("construtoras.id"), nullable=True)
    total_unidades  = Column(Integer, default=0)
    # Jardim das Flores: chave liberada só com assinatura (sem esperar cartório)
    chave_rapida    = Column(Boolean, default=False)
    ativo           = Column(Boolean, default=True)
    unidade_id      = Column(Integer, ForeignKey("unidades.id"), nullable=True)

    clientes        = relationship("Cliente", back_populates="empreendimento")
    unidade         = relationship("Unidade", back_populates="empreendimentos")
    construtora_rel = relationship("Construtora", back_populates="empreendimentos")


class Corretor(Base):
    __tablename__ = "corretores"

    id       = Column(Integer, primary_key=True, index=True)
    nome     = Column(String(120), nullable=False)
    creci    = Column(String(30))
    telefone = Column(String(20))
    ativo    = Column(Boolean, default=True)

    clientes = relationship("Cliente", back_populates="corretor")


class Analista(Base):
    __tablename__ = "analistas"

    id                  = Column(Integer, primary_key=True, index=True)
    nome                = Column(String(120), nullable=False)
    email               = Column(String(120))
    comissao_por_casa   = Column(Numeric(8, 2), default=80.00)  # R$ por processo assinado
    meta_mensal         = Column(Integer, default=20)            # meta de casas/mês
    ativo               = Column(Boolean, default=True)

    clientes = relationship("Cliente", back_populates="analista")


class Cliente(Base):
    __tablename__ = "clientes"

    id        = Column(Integer, primary_key=True, index=True)
    num_ordem = Column(String(10), nullable=False, unique=True, index=True)
    nome      = Column(String(180), nullable=False, index=True)
    cpf       = Column(String(14), nullable=False, unique=True, index=True)
    telefone  = Column(String(20))

    # Localização
    empreendimento_id = Column(Integer, ForeignKey("empreendimentos.id"), nullable=False)
    casa_num          = Column(String(10), nullable=False)
    logradouro        = Column(String(200))  # obrigatório para Jardim das Flores
    quadra            = Column(String(10))
    lote              = Column(String(10))

    # Agentes
    corretor_id = Column(Integer, ForeignKey("corretores.id"))
    analista_id = Column(Integer, ForeignKey("analistas.id"))

    # ── Datas do workflow ─────────────────────────────────────────
    data_assinatura      = Column(Date)   # Etapa 2: assinou na agência (gatilho comissão)
    data_siktd_ok        = Column(Date)   # Etapa 4: OK da Caixa no SIKTD
    data_cartorio_envio  = Column(Date)   # Etapa 5: quando enviou ao cartório
    chegada_cartorio     = Column(Date)   # Etapa 5: quando veio de volta (previsão ou real)
    doc_recebido         = Column(Boolean, default=False)
    data_doc_recebido    = Column(Date)   # data em que a garantia chegou

    chave_liberada       = Column(Boolean, default=False)  # chave física entregue ao cliente
    data_chave_liberada  = Column(Date)   # data da entrega da chave

    # ── Financeiro ────────────────────────────────────────────────
    valor_rcpm           = Column(Numeric(10, 2))
    valor_avaliacao      = Column(Numeric(12, 2))  # laudo do engenheiro
    valor_venda          = Column(Numeric(12, 2))  # valor real da venda

    # Arquivo
    pdf_path = Column(String(300))

    # Workflow e status
    workflow_step = Column(
        Enum(WorkflowStep), default=WorkflowStep.engenharia, nullable=False
    )
    status = Column(
        Enum(DocStatus), default=DocStatus.proximo, nullable=False
    )

    observacoes = Column(Text)

    ativo      = Column(Boolean, default=True, nullable=False)
    deleted_at = Column(DateTime, nullable=True)   # preenchido no soft-delete

    # Arquivamento: processo concluído e movido para a Base
    arquivado    = Column(Boolean, default=False, nullable=False)
    arquivado_em = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    empreendimento = relationship("Empreendimento", back_populates="clientes")
    corretor       = relationship("Corretor", back_populates="clientes")
    analista       = relationship("Analista", back_populates="clientes")
    logs           = relationship("LogAtividade", back_populates="cliente",
                                  order_by="LogAtividade.created_at.desc()", cascade="all, delete-orphan")
    notas          = relationship("Nota", back_populates="cliente",
                                  order_by="Nota.created_at.desc()", cascade="all, delete-orphan")


class TipoUsuario(str, enum.Enum):
    admin    = "admin"
    operador = "operador"


class Usuario(Base):
    __tablename__ = "usuarios"

    id         = Column(Integer, primary_key=True, index=True)
    nome       = Column(String(120), nullable=False)
    email      = Column(String(200), nullable=False, unique=True, index=True)
    senha_hash = Column(String(256), nullable=False)
    tipo       = Column(Enum(TipoUsuario), default=TipoUsuario.operador, nullable=False)
    ativo      = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class LogAtividade(Base):
    """Histórico de ações realizadas em um processo de cliente."""
    __tablename__ = "logs_atividade"

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)   # None = sistema
    acao       = Column(String(60), nullable=False)   # ex.: "workflow_alterado"
    detalhes   = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="logs")
    usuario = relationship("Usuario")


class Nota(Base):
    """Comentários/observações livres por cliente, feitos por usuários."""
    __tablename__ = "notas_clientes"

    id         = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    texto      = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="notas")
    usuario = relationship("Usuario")


class ComissaoLancamento(Base):
    """Lançamentos manuais de comissão (bônus, ajustes, extras)."""
    __tablename__ = "comissao_lancamentos"

    id           = Column(Integer, primary_key=True, index=True)
    analista_id  = Column(Integer, ForeignKey("analistas.id"), nullable=False)
    descricao    = Column(String(200), nullable=False)
    valor        = Column(Numeric(10, 2), nullable=False)
    data_ref     = Column(Date, nullable=False)   # mês de referência (qualquer dia do mês)
    pago         = Column(Boolean, default=False)
    data_pagamento = Column(Date)
    created_at   = Column(DateTime, default=datetime.utcnow)

    analista = relationship("Analista")
