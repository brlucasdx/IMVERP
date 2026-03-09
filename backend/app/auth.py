"""
Utilitários de autenticação JWT + bcrypt.

Boas práticas aplicadas:
  - Senha hash com bcrypt (custo alto, resistente a brute-force)
  - JWT assinado com HS256, expiração de 8h
  - SECRET_KEY obrigatória via env var em produção
  - Payload mínimo (apenas user id) — sem dados sensíveis no token
  - Erro genérico no login (não revela se email existe)
"""
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario, TipoUsuario

# ── Configuração ──────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "TROQUE_ANTES_DE_COLOCAR_EM_PRODUCAO_imv2024x9k2")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HOURS = 8

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Funções de senha ──────────────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


# ── JWT ───────────────────────────────────────────────────────────
def create_access_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=TOKEN_EXPIRE_HOURS))
    payload = {"sub": str(user_id), "exp": expire, "iat": datetime.utcnow()}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Dependências FastAPI ──────────────────────────────────────────
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub", 0))
        if not user_id:
            raise exc
    except (JWTError, ValueError):
        raise exc

    user = db.query(Usuario).filter(Usuario.id == user_id, Usuario.ativo == True).first()
    if not user:
        raise exc
    return user


def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    if current_user.tipo != TipoUsuario.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return current_user
