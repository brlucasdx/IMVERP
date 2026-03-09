"""Migration v2 — adiciona colunas arquivado e arquivado_em na tabela clientes."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    try:
        conn.execute(text(
            "ALTER TABLE clientes ADD COLUMN arquivado BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        print("  ✓  coluna 'arquivado' adicionada")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("  ⚠  coluna 'arquivado' já existe — pulando")
        else:
            raise

    try:
        conn.execute(text(
            "ALTER TABLE clientes ADD COLUMN arquivado_em TIMESTAMP"
        ))
        print("  ✓  coluna 'arquivado_em' adicionada")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("  ⚠  coluna 'arquivado_em' já existe — pulando")
        else:
            raise

    conn.commit()

print("\nMigration v2 concluída.")
