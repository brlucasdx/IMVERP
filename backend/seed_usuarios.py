"""Cria os usuários iniciais do sistema."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import bcrypt
from app.database import engine, Base, get_db
from app.models import Usuario, TipoUsuario
from sqlalchemy.orm import Session

def hash_senha(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

# Cria a tabela se não existir
Base.metadata.create_all(bind=engine)

usuarios = [
    {"nome": "Adriella",  "email": "adriella@imv.com",  "tipo": TipoUsuario.admin},
    {"nome": "Lucas",     "email": "lucas@imv.com",      "tipo": TipoUsuario.admin},
    {"nome": "Simone",    "email": "simone@imv.com",     "tipo": TipoUsuario.operador},
    {"nome": "Markele",   "email": "markele@imv.com",    "tipo": TipoUsuario.operador},
]

SENHA = "hn123"

with Session(engine) as db:
    for u in usuarios:
        existe = db.query(Usuario).filter(Usuario.email == u["email"]).first()
        if existe:
            print(f"  ⚠  {u['nome']} já existe — pulando")
            continue
        novo = Usuario(
            nome=u["nome"],
            email=u["email"],
            senha_hash=hash_senha(SENHA),
            tipo=u["tipo"],
        )
        db.add(novo)
        print(f"  ✓  {u['nome']} ({u['tipo'].value}) criado")
    db.commit()

print("\nPronto! Todos os usuários foram criados com senha: hn123")
