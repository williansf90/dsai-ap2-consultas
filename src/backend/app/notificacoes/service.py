"""Criação e gestão das notificações internas."""
from sqlalchemy.orm import Session

from app.agendamento.models import Consulta
from app.auth.models import Usuario
from app.notificacoes import textos
from app.notificacoes.models import Notificacao


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
