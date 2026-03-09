"""
Popula o banco com os dados de exemplo validados pela Adriella.
Execute: python seed.py
"""
from datetime import date, timedelta
from decimal import Decimal

from app.database import SessionLocal, engine, Base
from app.models import Empreendimento, Corretor, Analista, Cliente, DocStatus, WorkflowStep

Base.metadata.create_all(bind=engine)

hoje = date.today()

def seed():
    db = SessionLocal()

    if db.query(Cliente).count() > 0:
        print("Banco ja possui dados. Seed ignorado.")
        db.close()
        return

    print("Populando banco de dados...")

    # -- Empreendimentos
    empreendimentos = [
        Empreendimento(nome="Vila Imperador",     construtora="Construtora Alpha", total_unidades=212, chave_rapida=False),
        Empreendimento(nome="Jardim das Flores",  construtora="Construtora Beta",  total_unidades=148, chave_rapida=True),
        Empreendimento(nome="Japim",              construtora="Construtora Delta", total_unidades=87,  chave_rapida=False),
        Empreendimento(nome="Parque Palmeiras",   construtora="Construtora Gama",  total_unidades=95,  chave_rapida=False),
        Empreendimento(nome="Residencial Aurora", construtora="Construtora Delta", total_unidades=60,  chave_rapida=False),
    ]
    db.add_all(empreendimentos)
    db.flush()
    emp = {e.nome: e for e in empreendimentos}

    # -- Corretores
    corretores = [
        Corretor(nome="Leudo Gomes",   creci="12345-F"),
        Corretor(nome="Andrey Costa",  creci="23456-F"),
        Corretor(nome="Emerson Rios",  creci="34567-F"),
        Corretor(nome="Bruna Tavares", creci="45678-F"),
        Corretor(nome="Rafael Duarte", creci="56789-F"),
        Corretor(nome="Carla Moura",   creci="67890-F"),
    ]
    db.add_all(corretores)
    db.flush()
    cor = {c.nome: c for c in corretores}

    # -- Analistas
    analistas = [
        Analista(nome="Simone",   email="simone@imv.com.br",   comissao_por_casa=Decimal("80.00"), meta_mensal=20),
        Analista(nome="Markele",  email="markele@imv.com.br",  comissao_por_casa=Decimal("80.00"), meta_mensal=20),
        Analista(nome="Adriella", email="adriella@imv.com.br", comissao_por_casa=Decimal("80.00"), meta_mensal=25),
    ]
    db.add_all(analistas)
    db.flush()
    ana = {a.nome: a for a in analistas}

    # -- Clientes
    clientes_data = [
        # 001 - cartorio atrasado (envio ha 30 dias, chegada vencida)
        dict(num_ordem="001", nome="Carlos Andrade",  cpf="412.387.291-05",
             empreendimento_id=emp["Vila Imperador"].id, casa_num="12",
             logradouro="", quadra="B", lote="04",
             corretor_id=cor["Leudo Gomes"].id, analista_id=ana["Simone"].id,
             data_assinatura=date(2024, 2, 12),
             data_cartorio_envio=hoje - timedelta(days=30),
             chegada_cartorio=hoje - timedelta(days=5),
             doc_recebido=False, valor_rcpm=Decimal("820.00"),
             valor_avaliacao=Decimal("185000.00"), valor_venda=Decimal("180000.00"),
             workflow_step=WorkflowStep.cartorio, status=DocStatus.vencido),

        # 002 - cartorio, Jardim das Flores, chegada em 2 dias
        dict(num_ordem="002", nome="Fernanda Lima",   cpf="623.190.847-12",
             empreendimento_id=emp["Jardim das Flores"].id, casa_num="35",
             logradouro="Rua das Acacias, 88", quadra="A", lote="09",
             corretor_id=cor["Andrey Costa"].id, analista_id=ana["Markele"].id,
             data_assinatura=date(2024, 1, 15),
             data_cartorio_envio=hoje - timedelta(days=28),
             chegada_cartorio=hoje + timedelta(days=2),
             doc_recebido=False, valor_rcpm=Decimal("750.00"),
             valor_avaliacao=Decimal("160000.00"), valor_venda=Decimal("158000.00"),
             workflow_step=WorkflowStep.cartorio, status=DocStatus.proximo),

        # 003 - SIKTD OK, aguardando envio ao cartorio
        dict(num_ordem="003", nome="Ricardo Mendes",  cpf="109.874.562-33",
             empreendimento_id=emp["Japim"].id, casa_num="07",
             logradouro="", quadra="C", lote="02",
             corretor_id=cor["Emerson Rios"].id, analista_id=ana["Adriella"].id,
             data_assinatura=date(2024, 3, 10),
             data_siktd_ok=hoje - timedelta(days=3),
             chegada_cartorio=hoje + timedelta(days=22),
             doc_recebido=False, valor_rcpm=Decimal("690.00"),
             valor_avaliacao=Decimal("140000.00"), valor_venda=Decimal("138000.00"),
             workflow_step=WorkflowStep.siktd, status=DocStatus.proximo),

        # 004 - documentacao em andamento
        dict(num_ordem="004", nome="Ana Sousa",       cpf="780.231.654-77",
             empreendimento_id=emp["Parque Palmeiras"].id, casa_num="18",
             logradouro="", quadra="A", lote="12",
             corretor_id=cor["Bruna Tavares"].id, analista_id=ana["Simone"].id,
             data_assinatura=date(2024, 3, 20),
             chegada_cartorio=hoje + timedelta(days=18),
             doc_recebido=False, valor_rcpm=Decimal("880.00"),
             valor_avaliacao=Decimal("195000.00"), valor_venda=Decimal("192000.00"),
             workflow_step=WorkflowStep.documentacao, status=DocStatus.proximo),

        # 005 - concluido
        dict(num_ordem="005", nome="Paulo Ferreira",  cpf="345.612.099-44",
             empreendimento_id=emp["Vila Imperador"].id, casa_num="44",
             logradouro="", quadra="D", lote="07",
             corretor_id=cor["Leudo Gomes"].id, analista_id=ana["Markele"].id,
             data_assinatura=date(2024, 5, 5),
             data_siktd_ok=date(2024, 6, 1),
             data_cartorio_envio=date(2024, 6, 5),
             chegada_cartorio=date(2024, 7, 5),
             doc_recebido=True, data_doc_recebido=date(2024, 7, 4),
             valor_rcpm=Decimal("920.00"),
             valor_avaliacao=Decimal("210000.00"), valor_venda=Decimal("208000.00"),
             workflow_step=WorkflowStep.concluido, status=DocStatus.ok),

        # 006 - concluido, Jardim das Flores
        dict(num_ordem="006", nome="Marcia Oliveira", cpf="514.890.376-28",
             empreendimento_id=emp["Jardim das Flores"].id, casa_num="62",
             logradouro="Av. das Bromelias, 212", quadra="B", lote="15",
             corretor_id=cor["Rafael Duarte"].id, analista_id=ana["Adriella"].id,
             data_assinatura=date(2024, 6, 18),
             data_siktd_ok=date(2024, 7, 10),
             data_cartorio_envio=date(2024, 7, 15),
             chegada_cartorio=date(2024, 8, 15),
             doc_recebido=True, data_doc_recebido=date(2024, 8, 14),
             valor_rcpm=Decimal("810.00"),
             valor_avaliacao=Decimal("175000.00"), valor_venda=Decimal("173000.00"),
             workflow_step=WorkflowStep.concluido, status=DocStatus.ok),

        # 007 - cartorio, alerta 25d (envio ha 26 dias)
        dict(num_ordem="007", nome="Tiago Barbosa",   cpf="267.453.189-61",
             empreendimento_id=emp["Vila Imperador"].id, casa_num="91",
             logradouro="", quadra="A", lote="03",
             corretor_id=cor["Andrey Costa"].id, analista_id=ana["Simone"].id,
             data_assinatura=date(2024, 7, 22),
             data_cartorio_envio=hoje - timedelta(days=26),
             chegada_cartorio=hoje + timedelta(days=1),
             doc_recebido=False, valor_rcpm=Decimal("760.00"),
             valor_avaliacao=Decimal("165000.00"), valor_venda=Decimal("163000.00"),
             workflow_step=WorkflowStep.cartorio, status=DocStatus.proximo),

        # 008 - aprovacao Caixa
        dict(num_ordem="008", nome="Juliana Castro",  cpf="891.027.534-90",
             empreendimento_id=emp["Japim"].id, casa_num="14",
             logradouro="", quadra="C", lote="08",
             corretor_id=cor["Emerson Rios"].id, analista_id=ana["Markele"].id,
             data_assinatura=date(2024, 8, 30),
             doc_recebido=False, valor_rcpm=Decimal("840.00"),
             valor_avaliacao=Decimal("145000.00"), valor_venda=Decimal("143000.00"),
             workflow_step=WorkflowStep.aprovacao, status=DocStatus.proximo),

        # 009 - engenharia (laudo)
        dict(num_ordem="009", nome="Renato Silva",    cpf="433.761.805-19",
             empreendimento_id=emp["Parque Palmeiras"].id, casa_num="28",
             logradouro="", quadra="B", lote="11",
             corretor_id=cor["Bruna Tavares"].id, analista_id=ana["Adriella"].id,
             doc_recebido=False, valor_rcpm=Decimal("730.00"),
             valor_avaliacao=Decimal("155000.00"), valor_venda=Decimal("153000.00"),
             workflow_step=WorkflowStep.engenharia, status=DocStatus.proximo),

        # 010 - assinado esta semana (para relatorio Liberar Chaves)
        dict(num_ordem="010", nome="Cristiane Prado", cpf="672.345.917-83",
             empreendimento_id=emp["Vila Imperador"].id, casa_num="56",
             logradouro="", quadra="D", lote="19",
             corretor_id=cor["Leudo Gomes"].id, analista_id=ana["Simone"].id,
             data_assinatura=hoje - timedelta(days=2),
             doc_recebido=False, valor_rcpm=Decimal("950.00"),
             valor_avaliacao=Decimal("220000.00"), valor_venda=Decimal("218000.00"),
             workflow_step=WorkflowStep.aprovacao, status=DocStatus.proximo),

        # 011 - assinado ontem, Jardim das Flores (chave rapida)
        dict(num_ordem="011", nome="Bruno Almeida",   cpf="521.436.789-02",
             empreendimento_id=emp["Jardim das Flores"].id, casa_num="77",
             logradouro="Rua das Orquideas, 45", quadra="C", lote="06",
             corretor_id=cor["Carla Moura"].id, analista_id=ana["Adriella"].id,
             data_assinatura=hoje - timedelta(days=1),
             doc_recebido=False, valor_rcpm=Decimal("870.00"),
             valor_avaliacao=Decimal("170000.00"), valor_venda=Decimal("168000.00"),
             workflow_step=WorkflowStep.aprovacao, status=DocStatus.proximo),
    ]

    for data in clientes_data:
        db.add(Cliente(**data))

    db.commit()
    print(f"  {len(empreendimentos)} empreendimentos")
    print(f"  {len(corretores)} corretores")
    print(f"  {len(analistas)} analistas")
    print(f"  {len(clientes_data)} clientes")
    print("Seed concluido!")
    db.close()


if __name__ == "__main__":
    seed()
