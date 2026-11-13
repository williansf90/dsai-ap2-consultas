"""Check-in e atendimento: transições protegidas por lock na linha da consulta."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agendamento.models import Consulta
from app.core.erros import NaoEncontrado


def obter_para_transicao(db: Session, consulta_id: int) -> Consulta:
    """Consulta com SELECT ... FOR UPDATE OF consultas: serializa pedidos simultâneos.

    Dois pedidos concorrentes para a mesma consulta são serializados; o segundo lê o
    status já atualizado e é recusado pela tabela TRANSICOES (RegraViolada → 422).
    O `of=Consulta` evita o erro do PostgreSQL com os joins eager (lazy="joined").
    """
    consulta = db.scalar(select(Consulta).where(Consulta.id == consulta_id).with_for_update(of=Consulta))
    if consulta is None:
        raise NaoEncontrado("Consulta não encontrada.")
    return consulta
