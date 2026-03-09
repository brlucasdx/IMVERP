from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import Usuario, TipoUsuario
from app.auth import (
    verify_password, hash_password, create_access_token,
    get_current_user, require_admin,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ── Schemas ───────────────────────────────────────────────────────
class LoginIn(BaseModel):
    email: str
    senha: str


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    tipo: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str
    usuario: UsuarioOut


class UsuarioCreate(BaseModel):
    nome: str
    email: str
    senha: str
    tipo: TipoUsuario = TipoUsuario.operador


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    tipo: Optional[TipoUsuario] = None


class SenhaChange(BaseModel):
    senha_atual: Optional[str] = None  # obrigatório para não-admin
    senha_nova: str


# ── Endpoints públicos ────────────────────────────────────────────
@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    """Autenticação. Erro genérico para não revelar se email existe."""
    user = db.query(Usuario).filter(
        Usuario.email == data.email.lower().strip(),
        Usuario.ativo == True,
    ).first()

    # Verifica credenciais — erro propositalmente igual para email ou senha errados
    if not user or not verify_password(data.senha, user.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
        )

    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer", "usuario": user}


# ── Endpoints autenticados ────────────────────────────────────────
@router.get("/me", response_model=UsuarioOut)
def me(current_user: Usuario = Depends(get_current_user)):
    return current_user


# ── Gestão de usuários (admin only) ──────────────────────────────
@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_admin),
):
    return db.query(Usuario).filter(Usuario.ativo == True).order_by(Usuario.nome).all()


@router.post("/usuarios", response_model=UsuarioOut, status_code=201)
def criar_usuario(
    data: UsuarioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_admin),
):
    if db.query(Usuario).filter(Usuario.email == data.email.lower().strip()).first():
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    user = Usuario(
        nome=data.nome.strip(),
        email=data.email.lower().strip(),
        senha_hash=hash_password(data.senha),
        tipo=data.tipo,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/usuarios/{user_id}", response_model=UsuarioOut)
def atualizar_usuario(
    user_id: int,
    data: UsuarioUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    # Proteção: admin não pode rebaixar o próprio nível de acesso
    if current_user.id == user_id and data.tipo is not None and data.tipo != current_user.tipo:
        raise HTTPException(status_code=400, detail="Você não pode alterar seu próprio nível de acesso")

    user = db.query(Usuario).filter(Usuario.id == user_id, Usuario.ativo == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    if data.nome:
        user.nome = data.nome.strip()
    if data.email:
        conflict = db.query(Usuario).filter(
            Usuario.email == data.email.lower().strip(),
            Usuario.id != user_id,
        ).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Email já em uso por outro usuário")
        user.email = data.email.lower().strip()
    if data.tipo is not None:
        user.tipo = data.tipo

    db.commit()
    db.refresh(user)
    return user


@router.put("/usuarios/{user_id}/senha")
def alterar_senha(
    user_id: int,
    data: SenhaChange,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Usuário só pode alterar a própria senha; admin pode alterar qualquer uma
    if current_user.tipo != TipoUsuario.admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    user = db.query(Usuario).filter(Usuario.id == user_id, Usuario.ativo == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Não-admin deve confirmar a senha atual
    if current_user.tipo != TipoUsuario.admin:
        if not data.senha_atual or not verify_password(data.senha_atual, user.senha_hash):
            raise HTTPException(status_code=400, detail="Senha atual incorreta")

    user.senha_hash = hash_password(data.senha_nova)
    db.commit()
    return {"ok": True}


@router.delete("/usuarios/{user_id}")
def desativar_usuario(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta")

    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Não encontrado")

    user.ativo = False
    db.commit()
    return {"ok": True}
