"""Criação e gestão das notificações internas."""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.agendamento.models import Consulta
from app.auth.models import Usuario
from app.core.erros import NaoEncontrado
from app.core.paginacao import paginar
from app.core.tempo import agora_utc
from app.notificacoes import textos
from app.notificacoes.models import Notificacao

POR_PAGINA = 20


def criar(
    db: Session,
    usuario_id: int,
    tipo: str,
    consulta_id: int | None = None,
    variaveis: dict | None = None,
) -> Notificacao:
    """Insere sem commit: a notificação participa da transação de quem chama."""
    titulo, texto = textos.renderizar(tipo, variaveis or {})
    notificacao = Notificacao(
        usuario_id=usuario_id, tipo=tipo, titulo=titulo, texto=texto, consulta_id=consulta_id
    )
    db.add(notificacao)
    return notificacao


def notificar_consulta_marcada(db: Session, paciente: Usuario, consulta: Consulta) -> Notificacao:
    return criar(db, paciente.id, "consulta_marcada", consulta.id, variaveis={
        "profissional": consulta.profissional.nome,
        "tipo_consulta": consulta.tipo_consulta.nome,
        "unidade": consulta.unidade.nome,
        "data_hora": consulta.inicio,
    })


def notificar_consulta_remarcada(
    db: Session, paciente: Usuario, consulta_antiga: Consulta, consulta_nova: Consulta
) -> Notificacao:
    return criar(db, paciente.id, "consulta_remarcada", consulta_nova.id, variaveis={
        "profissional": consulta_nova.profissional.nome,
        "unidade": consulta_nova.unidade.nome,
        "data_hora": consulta_nova.inicio,
        "data_hora_antiga": consulta_antiga.inicio,
    })


def notificar_consulta_cancelada_clinica(db: Session, paciente: Usuario, consulta: Consulta) -> Notificacao:
    return criar(db, paciente.id, "consulta_cancelada", consulta.id, variaveis={
        "profissional": consulta.profissional.nome,
        "data_hora": consulta.inicio,
    })


# ---------- central do usuário ----------

def listar(db: Session, usuario: Usuario, pagina: int = 1, por_pagina: int = POR_PAGINA) -> dict:
    base = (
        select(Notificacao)
        .where(Notificacao.usuario_id == usuario.id)
        .order_by(Notificacao.id.desc())
    )
    dados = paginar(db, base, pagina, por_pagina)
    nao_lidas = db.scalar(
        select(func.count()).select_from(Notificacao)
        .where(Notificacao.usuario_id == usuario.id, Notificacao.lida_em.is_(None))
    ) or 0
    return {**dados, "nao_lidas": nao_lidas}


def marcar_lida(db: Session, usuario: Usuario, notificacao_id: int) -> Notificacao:
    notificacao = db.get(Notificacao, notificacao_id)
    if notificacao is None or notificacao.usuario_id != usuario.id:
        raise NaoEncontrado("Notificação não encontrada.")
    if notificacao.lida_em is None:
        notificacao.lida_em = agora_utc()
    db.commit()
    return notificacao


def marcar_todas_lidas(db: Session, usuario: Usuario) -> int:
    resultado = db.execute(
        update(Notificacao)
        .where(Notificacao.usuario_id == usuario.id, Notificacao.lida_em.is_(None))
        .values(lida_em=agora_utc())
    )
    db.commit()
    return resultado.rowcount
