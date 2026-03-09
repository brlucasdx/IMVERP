from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends
from app.auth import get_current_user
from app.database import get_db
from app.models import Analista
from app.schemas import AnalistaOut

router = APIRouter(prefix="/api/analistas", tags=["Analistas"])
router.dependencies.append(Depends(get_current_user))

@router.get("", response_model=list[AnalistaOut])
def listar(db: Session = Depends(get_db)):
    return db.query(Analista).filter(Analista.ativo == True).order_by(Analista.nome).all()
