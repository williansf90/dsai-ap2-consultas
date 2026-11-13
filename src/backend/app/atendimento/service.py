"""Check-in e atendimento: transições protegidas por lock na linha da consulta."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agendamento.models import Consulta
from app.agendamento.service import mudar_status
from app.auth.models import Usuario
from app.clinicas.models import Profissional
from app.core.erros import NaoEncontrado, Proibido, RegraViolada
from app.core.tempo import FUSO_LOCAL, agora_utc

ANTECEDENCIA_CHECK_IN = timedelta(hours=1)
MAX_ANOTACAO = 5000


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


def finalizar(db: Session, consulta_id: int, autor: Usuario, anotacao: str) -> Consulta:
    """em_atendimento → realizada; anotação obrigatória, não vazia e ≤ 5.000; grava fim."""
    consulta = obter_para_transicao(db, consulta_id)
    if consulta.profissional.usuario_id != autor.id:
        raise Proibido("Somente o profissional desta consulta pode finalizar o atendimento.")
    texto = anotacao.strip()
    if not texto:
        raise RegraViolada("Informe a anotação do atendimento.")
    if len(texto) > MAX_ANOTACAO:
        raise RegraViolada(f"A anotação deve ter no máximo {MAX_ANOTACAO} caracteres.")
    mudar_status(db, consulta, "realizada", autor)
    consulta.atendimento_fim = agora_utc()
    consulta.anotacao = texto
    db.commit()
    return consulta


def anotacao(db: Session, consulta_id: int, autor: Usuario) -> str | None:
    """Anotação visível só para o profissional da consulta e para quem compartilha especialidade."""
    consulta = db.get(Consulta, consulta_id)
    if consulta is None:
        raise NaoEncontrado("Consulta não encontrada.")
    if consulta.profissional.usuario_id == autor.id:
        return consulta.anotacao
    if autor.perfil != "profissional":
        raise Proibido("Esta anotação não está disponível para o seu perfil.")
    eu = db.scalar(select(Profissional).where(Profissional.usuario_id == autor.id))
    minhas = {e.id for e in eu.especialidades} if eu else set()
    em_comum = {e.id for e in consulta.profissional.especialidades} & minhas
    if not em_comum:
        raise Proibido("Esta anotação não está disponível para o seu perfil.")
    return consulta.anotacao
