"""Check-in e atendimento: transições protegidas por lock na linha da consulta."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agendamento.models import Consulta
from app.agendamento.service import mudar_status
from app.auth.models import Usuario
from app.core.erros import NaoEncontrado, Proibido, RegraViolada
from app.core.tempo import FUSO_LOCAL, agora_utc

ANTECEDENCIA_CHECK_IN = timedelta(hours=1)


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


def check_in(db: Session, consulta_id: int, autor: Usuario) -> Consulta:
    """marcada → confirmada no dia da consulta, a partir de 1 hora antes; grava chegada_em."""
    consulta = obter_para_transicao(db, consulta_id)
    if autor.perfil == "paciente" and consulta.paciente_id != autor.id:
        raise NaoEncontrado("Consulta não encontrada.")
    agora = agora_utc()
    no_dia = agora.astimezone(FUSO_LOCAL).date() == consulta.inicio.astimezone(FUSO_LOCAL).date()
    if not no_dia or agora < consulta.inicio - ANTECEDENCIA_CHECK_IN:
        raise RegraViolada("O check-in só é possível no dia da consulta, a partir de 1 hora antes do horário.")
    mudar_status(db, consulta, "confirmada", autor)
    consulta.chegada_em = agora
    db.commit()
    return consulta


def chamar(db: Session, consulta_id: int, autor: Usuario) -> Consulta:
    """confirmada → em_atendimento; só o profissional dono; grava atendimento_inicio."""
    consulta = obter_para_transicao(db, consulta_id)
    if consulta.profissional.usuario_id != autor.id:
        raise Proibido("Somente o profissional desta consulta pode chamar o paciente.")
    mudar_status(db, consulta, "em_atendimento", autor)
    consulta.atendimento_inicio = agora_utc()
    db.commit()
    return consulta
