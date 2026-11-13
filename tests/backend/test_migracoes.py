"""Migrações Alembic: a cadeia completa aplica do zero num banco temporário e reverte."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from apoio import (
    criar_consulta,
    criar_especialidade,
    criar_profissional,
    criar_unidade,
    criar_usuario,
    local,
)

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "src" / "backend"
BANCO_MIGRACAO = "marcaconsulta_migracao"
REVISAO_ANTERIOR = "c8aaa33475a5"
REVISAO_NOTIFICACOES = "b7e3f9a2d1c4"


@pytest.fixture(scope="module")
def url_migracao():
    """Banco temporário, recriado do zero, separado do banco dos demais testes."""
    import pgserver

    servidor = pgserver.get_server(os.path.join(tempfile.gettempdir(), "marcaconsulta-pg"), cleanup_mode=None)
    servidor.psql(f"drop database if exists {BANCO_MIGRACAO};")
    servidor.psql(f"create database {BANCO_MIGRACAO};")
    return servidor.get_uri(BANCO_MIGRACAO)


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=True,
    )


def _conectar(url: str):
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            url = "postgresql+psycopg://" + url[len(prefixo):]
    return create_engine(url)


def _tabela_existe(conn, tabela: str) -> bool:
    return conn.execute(
        text("select exists(select 1 from information_schema.tables where table_name = :t)"),
        {"t": tabela},
    ).scalar_one()


def _definicao_check_tipo(conn) -> str:
    return conn.execute(text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid = 'notificacoes'::regclass and conname = 'ck_notificacoes_tipo'"
    )).scalar_one()


def test_migracoes_criam_notificacoes_com_check_e_revertem(url_migracao):
    _alembic(url_migracao, "upgrade", "head")
    with _conectar(url_migracao).connect() as conn:
        assert _tabela_existe(conn, "notificacoes")
        definicao = _definicao_check_tipo(conn)
        assert all(tipo in definicao for tipo in ("consulta_marcada", "consulta_remarcada", "consulta_cancelada"))
    _alembic(url_migracao, "downgrade", REVISAO_ANTERIOR)
    with _conectar(url_migracao).connect() as conn:
        assert not _tabela_existe(conn, "notificacoes")


def _colunas_de(conn, tabela: str) -> list[str]:
    return conn.execute(text(
        "select column_name from information_schema.columns where table_name = :t"
    ), {"t": tabela}).scalars().all()


def test_migracao_de_atendimento_cria_colunas_e_vinculo_e_reverte(url_migracao):
    _alembic(url_migracao, "upgrade", "head")
    with _conectar(url_migracao).connect() as conn:
        assert _tabela_existe(conn, "recepcao_unidade")
        colunas = _colunas_de(conn, "consultas")
        for coluna in ("chegada_em", "atendimento_inicio", "atendimento_fim", "anotacao"):
            assert coluna in colunas
        definicao = conn.execute(text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid = 'consultas'::regclass and conname = 'ck_consultas_anotacao'"
        )).scalar_one()
        assert "char_length" in definicao and "5000" in definicao
    _alembic(url_migracao, "downgrade", REVISAO_NOTIFICACOES)
    with _conectar(url_migracao).connect() as conn:
        assert not _tabela_existe(conn, "recepcao_unidade")
        colunas = _colunas_de(conn, "consultas")
        for coluna in ("chegada_em", "atendimento_inicio", "atendimento_fim", "anotacao"):
            assert coluna not in colunas


def test_check_de_anotacao_recusa_acima_de_5000_no_banco(db):
    """O CHECK do modelo (mesma definição da migração) recusa anotação > 5.000."""
    centro = criar_unidade(db)
    esp = criar_especialidade(db, tipos=(("Consulta", 30, 25000),))
    prof = criar_profissional(db, especialidades=[esp], unidades=[centro])
    paciente = criar_usuario(db)
    consulta = criar_consulta(db, paciente, prof, centro, esp.tipos[0], local("2026-10-12 09:00"))
    consulta.anotacao = "x" * 5001
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    consulta.anotacao = "x" * 5000  # no limite, passa
    db.commit()
