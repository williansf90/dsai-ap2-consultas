"""Spec: check-in e atendimento — transições, autorizações, fila, anotação e comprovante."""
from threading import Barrier, Thread

import pytest

from app.agendamento.models import HistoricoStatus
from app.agendamento.service import mudar_status
from app.atendimento.service import obter_para_transicao
from app.auth.models import Usuario
from app.core.db import SessionLocal
from app.core.erros import NaoEncontrado, RegraViolada
from app.core.tempo import Relogio
from apoio import (
    auth,
    criar_consulta,
    criar_especialidade,
    criar_faixa,
    criar_profissional,
    criar_unidade,
    criar_usuario,
    local,
)

SEG = "2026-10-12"  # segunda-feira


@pytest.fixture
def c(db):
    """Dia da consulta, 08:00. Profissional com usuário vinculado atende na Unidade Centro."""
    Relogio.atual = local(f"{SEG} 08:00")
    centro = criar_unidade(db)
    esp = criar_especialidade(db, tipos=(("Consulta", 30, 25000),))
    prof_usuario = criar_usuario(db, "profissional", nome="Dr. João Souza")
    prof = criar_profissional(db, especialidades=[esp], unidades=[centro], usuario=prof_usuario)
    criar_faixa(db, prof, centro, 0)
    paciente = criar_usuario(db, nome="Maria Paciente")
    consulta = criar_consulta(db, paciente, prof, centro, esp.tipos[0], local(f"{SEG} 09:00"))
    return {"prof": prof, "prof_usuario": prof_usuario, "centro": centro, "tipo": esp.tipos[0],
            "paciente": paciente, "recepcao": criar_usuario(db, "recepcao"),
            "admin": criar_usuario(db, "admin"), "consulta": consulta, "esp": esp}


# ---------- transições concorrentes (lock na linha) ----------

def test_transicoes_simultaneas_so_uma_vence(db, c):
    consulta_id = c["consulta"].id
    recepcao_id = c["recepcao"].id
    barreira = Barrier(2)
    resultados = []

    def confirmar():
        with SessionLocal() as s:
            autor = s.get(Usuario, recepcao_id)
            barreira.wait()
            try:
                consulta = obter_para_transicao(s, consulta_id)
                mudar_status(s, consulta, "confirmada", autor)
                s.commit()
                resultados.append("ok")
            except RegraViolada:
                s.rollback()
                resultados.append("conflito")

    threads = [Thread(target=confirmar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(resultados) == ["conflito", "ok"]
    assert db.query(HistoricoStatus).filter_by(consulta_id=consulta_id).count() == 1
    db.refresh(c["consulta"])
    assert c["consulta"].status == "confirmada"


def test_transicao_de_consulta_inexistente_devolve_404(db):
    with pytest.raises(NaoEncontrado) as erro:
        obter_para_transicao(db, 999999)
    assert erro.value.status_code == 404
