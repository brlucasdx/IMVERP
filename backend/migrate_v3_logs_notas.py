"""Migration v3 — cria tabelas logs_atividade e notas_clientes."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, Base
# Importar os modelos garante que as tabelas sejam registradas no metadata
from app.models import LogAtividade, Nota  # noqa: F401

Base.metadata.create_all(bind=engine, checkfirst=True)
print("Migration v3 concluída — tabelas logs_atividade e notas_clientes criadas.")
