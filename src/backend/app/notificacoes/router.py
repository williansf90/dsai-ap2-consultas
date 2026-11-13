from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.seguranca import usuario_atual
from app.notificacoes import service
from app.notificacoes.schemas import ListaNotificacoes, NotificacaoOut

router = APIRouter(tags=["notificacoes"])


@router.get("/notificacoes", response_model=ListaNotificacoes)
def listar(
    pagina: int = 1,
    por_pagina: int = service.POR_PAGINA,
    usuario=Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    return service.listar(db, usuario, pagina, por_pagina)


@router.patch("/notificacoes/{notificacao_id}/lida", response_model=NotificacaoOut)
def marcar_lida(notificacao_id: int, usuario=Depends(usuario_atual), db: Session = Depends(get_db)):
    return service.marcar_lida(db, usuario, notificacao_id)


@router.post("/notificacoes/marcar-todas-lidas")
def marcar_todas(usuario=Depends(usuario_atual), db: Session = Depends(get_db)):
    return {"atualizadas": service.marcar_todas_lidas(db, usuario)}
