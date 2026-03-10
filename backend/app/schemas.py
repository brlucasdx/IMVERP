from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator
from app.models import DocStatus, WorkflowStep


# ── Unidade ───────────────────────────────────────────────────────
class UnidadeCreate(BaseModel):
    nome: str
    cidade: str
    estado: str

class UnidadeUpdate(BaseModel):
    nome: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None

class UnidadeOut(BaseModel):
    id: int
    nome: str
    cidade: str
    estado: str
    ativo: bool
    total_empreendimentos: int = 0
    total_clientes: int = 0
    model_config = {"from_attributes": True}


# ── Construtora ───────────────────────────────────────────────────
class ConstrutoraCriar(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    responsavel: Optional[str] = None

class ConstrutorUpdate(BaseModel):
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    responsavel: Optional[str] = None

class ConstrutorOut(BaseModel):
    id: int
    nome: str
    cnpj: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    responsavel: Optional[str] = None
    ativo: bool
    total_empreendimentos: int = 0
    model_config = {"from_attributes": True}


# ── Empreendimento ────────────────────────────────────────────────
class EmpreendimentoBase(BaseModel):
    nome: str
    construtora: Optional[str] = None
    construtora_id: Optional[int] = None
    total_unidades: int = 0
    chave_rapida: bool = False
    unidade_id: Optional[int] = None

class EmpreendimentoCreate(EmpreendimentoBase):
    pass

class EmpreendimentoUpdate(BaseModel):
    nome: Optional[str] = None
    construtora: Optional[str] = None
    construtora_id: Optional[int] = None
    total_unidades: Optional[int] = None
    chave_rapida: Optional[bool] = None
    unidade_id: Optional[int] = None

class EmpreendimentoOut(EmpreendimentoBase):
    id: int
    ativo: bool
    total_clientes: int = 0
    unidade_nome: Optional[str] = None
    unidade_cidade: Optional[str] = None
    model_config = {"from_attributes": True}


# ── Corretor ──────────────────────────────────────────────────────
class CorretorBase(BaseModel):
    nome: str
    creci: Optional[str] = None
    telefone: Optional[str] = None

class CorretorUpdate(BaseModel):
    nome: Optional[str] = None
    creci: Optional[str] = None
    telefone: Optional[str] = None

class CorretorOut(CorretorBase):
    id: int
    ativo: bool
    total_vendas: int = 0
    model_config = {"from_attributes": True}


# ── Analista ──────────────────────────────────────────────────────
class AnalistaBase(BaseModel):
    nome: str
    email: Optional[str] = None

class AnalistaOut(AnalistaBase):
    id: int
    ativo: bool
    comissao_por_casa: Optional[Decimal] = None
    meta_mensal: int = 20
    model_config = {"from_attributes": True}

class AnalistaCarga(BaseModel):
    id: int
    nome: str
    total: int
    concluidos: int
    pendentes: int
    atrasados: int


# ── Cliente ───────────────────────────────────────────────────────
class ClienteCreate(BaseModel):
    num_ordem: str
    nome: str
    cpf: str
    telefone: Optional[str] = None
    empreendimento_id: int
    casa_num: str
    logradouro: Optional[str] = None
    quadra: Optional[str] = None
    lote: Optional[str] = None
    corretor_id: Optional[int] = None
    analista_id: Optional[int] = None
    data_assinatura: Optional[date] = None
    data_siktd_ok: Optional[date] = None
    data_cartorio_envio: Optional[date] = None
    chegada_cartorio: Optional[date] = None
    doc_recebido: bool = False
    data_doc_recebido: Optional[date] = None
    valor_rcpm: Optional[Decimal] = None
    valor_avaliacao: Optional[Decimal] = None
    valor_venda: Optional[Decimal] = None
    observacoes: Optional[str] = None
    chave_liberada: bool = False
    data_chave_liberada: Optional[date] = None
    workflow_step: WorkflowStep = WorkflowStep.engenharia
    status: DocStatus = DocStatus.proximo

    @field_validator("cpf")
    @classmethod
    def cpf_format(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    logradouro: Optional[str] = None
    quadra: Optional[str] = None
    lote: Optional[str] = None
    corretor_id: Optional[int] = None
    analista_id: Optional[int] = None
    data_assinatura: Optional[date] = None
    data_siktd_ok: Optional[date] = None
    data_cartorio_envio: Optional[date] = None
    chegada_cartorio: Optional[date] = None
    doc_recebido: Optional[bool] = None
    data_doc_recebido: Optional[date] = None
    valor_rcpm: Optional[Decimal] = None
    valor_avaliacao: Optional[Decimal] = None
    valor_venda: Optional[Decimal] = None
    observacoes: Optional[str] = None
    chave_liberada: Optional[bool] = None
    data_chave_liberada: Optional[date] = None
    workflow_step: Optional[WorkflowStep] = None
    status: Optional[DocStatus] = None


class ClienteOut(BaseModel):
    id: int
    num_ordem: str
    nome: str
    cpf: str
    telefone: Optional[str]
    casa_num: str
    logradouro: Optional[str]
    quadra: Optional[str]
    lote: Optional[str]
    data_assinatura: Optional[date]
    data_siktd_ok: Optional[date]
    data_cartorio_envio: Optional[date]
    chegada_cartorio: Optional[date]
    doc_recebido: bool
    data_doc_recebido: Optional[date]
    chave_liberada: bool
    data_chave_liberada: Optional[date]
    valor_rcpm: Optional[Decimal]
    valor_avaliacao: Optional[Decimal]
    valor_venda: Optional[Decimal]
    observacoes: Optional[str]
    pdf_path: Optional[str]
    workflow_step: WorkflowStep
    status: DocStatus
    ativo: bool = True
    arquivado: bool = False
    arquivado_em: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    empreendimento: Optional[EmpreendimentoOut]
    corretor: Optional[CorretorOut]
    analista: Optional[AnalistaOut]

    model_config = {"from_attributes": True}


# ── PDFs do cliente ───────────────────────────────────────────────
class ClientePdfOut(BaseModel):
    id: int
    filename: str
    tamanho: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Logs e Notas ──────────────────────────────────────────────────
class UsuarioMinOut(BaseModel):
    id: int
    nome: str
    model_config = {"from_attributes": True}

class LogOut(BaseModel):
    id: int
    acao: str
    detalhes: Optional[str]
    created_at: datetime
    usuario: Optional[UsuarioMinOut] = None
    model_config = {"from_attributes": True}

class NotaCreate(BaseModel):
    texto: str

class NotaOut(BaseModel):
    id: int
    texto: str
    created_at: datetime
    usuario: Optional[UsuarioMinOut] = None
    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────
class FunilStep(BaseModel):
    step: str
    label: str
    count: int

class RankingCorretorMes(BaseModel):
    nome: str
    total: int
    empreendimento_principal: str

class RelatorioEmpItem(BaseModel):
    empreendimento: str
    total_ativos: int
    assinaturas_mes: int
    rcpm_mes: Decimal
    concluidos: int
    em_cartorio: int
    atrasados: int

class RelatorioMensalOut(BaseModel):
    mes_referencia: str
    total_assinaturas: int
    total_rcpm: Decimal
    total_concluidos: int
    por_empreendimento: list[RelatorioEmpItem]
    ranking_corretores: list[RankingCorretorMes]

class PipelineEtapaItem(BaseModel):
    step: str
    label: str
    processos: int       # quantos processos passaram por esta etapa
    media_dias: float    # média de dias nesta etapa
    min_dias: int
    max_dias: int

class PipelineDuracaoOut(BaseModel):
    total_processos: int
    etapas: list[PipelineEtapaItem]

class KpiDashboard(BaseModel):
    total_vendas: int
    top_corretor: str
    top_corretor_vendas: int
    docs_aguardados_semana: int
    docs_recebidos_semana: int
    processos_pendentes: int
    processos_atrasados: int


class RankingCorretor(BaseModel):
    id: int
    nome: str
    total_vendas: int
    empreendimento_principal: str


class AlertaCartorio(BaseModel):
    cliente_id: int
    nome: str
    empreendimento: str
    chegada_cartorio: Optional[date]
    dias_cartorio: Optional[int]   # dias desde envio ao cartório
    doc_recebido: bool
    status: str


class DashboardOut(BaseModel):
    kpis: KpiDashboard
    ranking_corretores: list[RankingCorretor]
    carga_analistas: list[AnalistaCarga]
    alertas_cartorio: list[AlertaCartorio]
    funil_workflow: list[FunilStep]
    ranking_semanal: list[RankingCorretorMes]


# ── RCPM ──────────────────────────────────────────────────────────
class ConciliacaoConstrutora(BaseModel):
    construtora: str
    empreendimento: str
    total_apolices: int
    valor_cartao: Decimal
    valor_cobrado: Decimal
    diferenca: Decimal
    status: str


# ── Comissões ─────────────────────────────────────────────────────
class ComissaoAnalista(BaseModel):
    analista_id: int
    nome: str
    meta_mensal: int
    comissao_por_casa: Decimal
    casas_assinadas_mes: int
    valor_acumulado: Decimal
    percentual_meta: float       # 0‒100+
    status_meta: str             # "abaixo" | "ok" | "superou"


class ComissoesOut(BaseModel):
    mes_referencia: str           # "2026-03"
    analistas: list[ComissaoAnalista]
    total_assinaturas_mes: int
    total_comissoes: Decimal


class ComissaoCorretor(BaseModel):
    corretor_id: int
    nome: str
    meta_mensal: int
    comissao_por_venda: Decimal
    vendas_mes: int
    valor_acumulado: Decimal
    percentual_meta: float
    status_meta: str             # "abaixo" | "ok" | "superou"

class ComissoesCorretoresOut(BaseModel):
    mes_referencia: str
    corretores: list[ComissaoCorretor]
    total_vendas_mes: int
    total_comissoes: Decimal


# ── Lançamentos manuais de comissão ───────────────────────────────
class LancamentoCreate(BaseModel):
    analista_id: int
    descricao: str
    valor: Decimal
    data_ref: date   # qualquer dia do mês de referência

class LancamentoOut(BaseModel):
    id: int
    analista_id: int
    analista_nome: str
    descricao: str
    valor: Decimal
    data_ref: date
    pago: bool
    data_pagamento: Optional[date] = None
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Chaves ────────────────────────────────────────────────────────
class ClienteChave(BaseModel):
    id: int
    num_ordem: str
    nome: str
    empreendimento: str
    casa_num: str
    logradouro: Optional[str]
    data_assinatura: Optional[date]
    chave_rapida: bool            # True = Jardim das Flores
    doc_recebido: bool
    chave_liberada: bool
    data_chave_liberada: Optional[date]
    status_chave: str             # 'apto' | 'aguardando' | 'liberada'
    workflow_step: str            # valor atual do workflow
    corretor: Optional[str]
    analista: Optional[str]
