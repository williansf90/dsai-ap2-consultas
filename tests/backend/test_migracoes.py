"""Migrações Alembic: a cadeia completa aplica do zero num banco temporário e reverte."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "src" / "backend"
BANCO_MIGRACAO = "marcaconsulta_migracao"
REVISAO_ANTERIOR = "c8aaa33475a5"


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
