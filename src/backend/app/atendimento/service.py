"""Check-in e atendimento: transições protegidas por lock na linha da consulta."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.agendamento.models import Consulta
from app.agendamento.service import com_permissoes, mudar_status
from app.atendimento.models import recepcao_unidade
from app.auth.models import Usuario
from app.clinicas.models import Profissional, Unidade
from app.core.erros import NaoEncontrado, Proibido, RegraViolada
from app.core.tempo import FUSO_LOCAL, agora_utc

ANTECEDENCIA_CHECK_IN = timedelta(hours=1)
ANTECEDENCIA_FALTA = timedelta(minutes=30)
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


def marcar_faltou(db: Session, consulta_id: int, autor: Usuario) -> Consulta:
    """marcada → faltou, a partir de 30 minutos após o horário da consulta."""
    consulta = obter_para_transicao(db, consulta_id)
    if agora_utc() < consulta.inicio + ANTECEDENCIA_FALTA:
        raise RegraViolada("Só é possível marcar falta 30 minutos após o horário da consulta.")
    mudar_status(db, consulta, "faltou", autor)
    db.commit()
    return consulta


# ---------- fila do dia ----------

def unidades_permitidas(db: Session, usuario: Usuario) -> list[Unidade]:
    """Admin vê todas as unidades ativas; recepção, só as vinculadas."""
    base = select(Unidade).where(Unidade.ativa.is_(True)).order_by(Unidade.nome)
    if usuario.perfil == "admin":
        return list(db.scalars(base))
    ids = db.scalars(
        select(recepcao_unidade.c.unidade_id).where(recepcao_unidade.c.usuario_id == usuario.id)
    ).all()
    if not ids:
        return []
    return list(db.scalars(base.where(Unidade.id.in_(ids))))


def _validar_acesso_unidade(db: Session, usuario: Usuario, unidade_id: int) -> Unidade:
    unidade = db.get(Unidade, unidade_id)
    if unidade is None or not unidade.ativa:
        raise NaoEncontrado("Unidade não encontrada.")
    if usuario.perfil != "admin":
        vinculada = db.scalar(select(recepcao_unidade.c.unidade_id).where(
            recepcao_unidade.c.usuario_id == usuario.id,
            recepcao_unidade.c.unidade_id == unidade_id,
        ))
        if vinculada is None:
            raise Proibido("Você não tem acesso à fila desta unidade.")
    return unidade


def fila_do_dia(db: Session, usuario: Usuario, unidade_id: int, dia: date) -> list[dict]:
    """Consultas do dia/unidade ordenadas por horário, com flags de ação."""
    _validar_acesso_unidade(db, usuario, unidade_id)
    inicio = datetime.combine(dia, time.min, FUSO_LOCAL)
    fim = inicio + timedelta(days=1)
    consultas = db.scalars(
        select(Consulta)
        .where(Consulta.unidade_id == unidade_id, Consulta.inicio >= inicio, Consulta.inicio < fim)
        .order_by(Consulta.inicio)
    ).all()
    agora = agora_utc()
    itens = []
    for consulta in consultas:
        itens.append({
            **com_permissoes(consulta, usuario),
            "chegada_em": consulta.chegada_em,
            "pode_check_in": (
                consulta.status == "marcada"
                and agora.astimezone(FUSO_LOCAL).date() == dia
                and agora >= consulta.inicio - ANTECEDENCIA_CHECK_IN
            ),
            "pode_faltou": (
                consulta.status == "marcada" and agora >= consulta.inicio + ANTECEDENCIA_FALTA
            ),
        })
    return itens


# ---------- vínculo recepção ↔ unidade (admin) ----------

def vinculos_recepcao(db: Session) -> list[dict]:
    usuarios = list(db.scalars(
        select(Usuario).where(Usuario.perfil == "recepcao", Usuario.ativo.is_(True)).order_by(Usuario.nome)
    ))
    pares = db.execute(select(recepcao_unidade.c.usuario_id, recepcao_unidade.c.unidade_id)).all()
    mapa: dict[int, list[int]] = {}
    for usuario_id, unidade_id in pares:
        mapa.setdefault(usuario_id, []).append(unidade_id)
    return [
        {"usuario": {"id": u.id, "nome": u.nome, "email": u.email},
         "unidade_ids": sorted(mapa.get(u.id, []))}
        for u in usuarios
    ]


def _validar_vinculo(db: Session, usuario_id: int, unidade_id: int) -> None:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or usuario.perfil != "recepcao" or not usuario.ativo:
        raise NaoEncontrado("Recepção não encontrada.")
    unidade = db.get(Unidade, unidade_id)
    if unidade is None or not unidade.ativa:
        raise NaoEncontrado("Unidade não encontrada.")


def vincular(db: Session, usuario_id: int, unidade_id: int) -> dict:
    _validar_vinculo(db, usuario_id, unidade_id)
    db.execute(
        pg_insert(recepcao_unidade)
        .values(usuario_id=usuario_id, unidade_id=unidade_id)
        .on_conflict_do_nothing()
    )
    db.commit()
    return next(v for v in vinculos_recepcao(db) if v["usuario"]["id"] == usuario_id)


def desvincular(db: Session, usuario_id: int, unidade_id: int) -> None:
    resultado = db.execute(delete(recepcao_unidade).where(
        recepcao_unidade.c.usuario_id == usuario_id,
        recepcao_unidade.c.unidade_id == unidade_id,
    ))
    if resultado.rowcount == 0:
        raise NaoEncontrado("Vínculo não encontrado.")
    db.commit()


# ---------- comprovante de comparecimento ----------

def comprovante(db: Session, consulta_id: int, paciente: Usuario) -> bytes:
    """PDF de consulta realizada, disponível apenas para o paciente dono."""
    from app.atendimento.comprovante import gerar_comprovante

    consulta = db.get(Consulta, consulta_id)
    if consulta is None or consulta.paciente_id != paciente.id:
        raise NaoEncontrado("Consulta não encontrada.")
    if consulta.status != "realizada":
        raise RegraViolada("O comprovante só está disponível para consultas realizadas.")
    return gerar_comprovante(consulta)
