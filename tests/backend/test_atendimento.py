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


# ---------- check-in ----------

def check_in(client, consulta_id, usuario):
    return client.post(f"/api/consultas/{consulta_id}/check-in", headers=auth(usuario))


def test_paciente_faz_check_in_no_dia_e_registra_chegada(client, db, c):
    Relogio.atual = local(f"{SEG} 08:30")
    r = check_in(client, c["consulta"].id, c["paciente"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmada"
    db.refresh(c["consulta"])
    assert c["consulta"].chegada_em == Relogio.atual
    ultimo = (
        db.query(HistoricoStatus)
        .filter_by(consulta_id=c["consulta"].id)
        .order_by(HistoricoStatus.id.desc())
        .first()
    )
    assert (ultimo.para_status, ultimo.usuario_id) == ("confirmada", c["paciente"].id)


@pytest.mark.parametrize("perfil", ["recepcao", "admin"])
def test_recepcao_e_admin_tambem_fazem_check_in(client, c, perfil):
    r = check_in(client, c["consulta"].id, c[perfil])
    assert r.status_code == 200 and r.json()["status"] == "confirmada"


def test_check_in_antes_de_uma_hora_do_horario_devolve_422(client, c):
    Relogio.atual = local(f"{SEG} 07:00")
    r = check_in(client, c["consulta"].id, c["paciente"])
    assert r.status_code == 422
    assert "1 hora" in r.json()["detail"]


def test_check_in_em_outro_dia_devolve_422(client, c):
    Relogio.atual = local("2026-10-13 08:00")
    r = check_in(client, c["consulta"].id, c["paciente"])
    assert r.status_code == 422


def test_check_in_duplicado_devolve_422_e_mantem_a_primeira_chegada(client, db, c):
    assert check_in(client, c["consulta"].id, c["paciente"]).status_code == 200
    db.refresh(c["consulta"])
    primeira_chegada = c["consulta"].chegada_em
    r = check_in(client, c["consulta"].id, c["recepcao"])
    assert r.status_code == 422
    db.refresh(c["consulta"])
    assert c["consulta"].chegada_em == primeira_chegada


def test_check_in_de_consulta_cancelada_devolve_422(client, c):
    r = client.post(f"/api/consultas/{c['consulta'].id}/cancelar", headers=auth(c["recepcao"]))
    assert r.status_code == 200
    assert check_in(client, c["consulta"].id, c["paciente"]).status_code == 422


def test_check_in_de_outro_paciente_devolve_404(client, db, c):
    assert check_in(client, c["consulta"].id, criar_usuario(db, nome="Intruso")).status_code == 404


def test_profissional_nao_faz_check_in_devolve_403(client, c):
    assert check_in(client, c["consulta"].id, c["prof_usuario"]).status_code == 403


def test_dois_check_ins_simultaneos_so_um_vence(c):
    from fastapi.testclient import TestClient

    from app.main import app

    barreira = Barrier(2)
    respostas = []

    def tentar(usuario):
        cliente = TestClient(app)
        barreira.wait()
        r = cliente.post(f"/api/consultas/{c['consulta'].id}/check-in", headers=auth(usuario))
        respostas.append(r.status_code)

    threads = [Thread(target=tentar, args=(u,)) for u in (c["paciente"], c["recepcao"])]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(respostas) == [200, 422]


# ---------- chamar ----------

def chamar(client, consulta_id, usuario):
    return client.post(f"/api/consultas/{consulta_id}/chamar", headers=auth(usuario))


def preparar_confirmada(client, c):
    assert check_in(client, c["consulta"].id, c["paciente"]).status_code == 200


def test_profissional_dono_chama_e_registra_inicio(client, db, c):
    preparar_confirmada(client, c)
    r = chamar(client, c["consulta"].id, c["prof_usuario"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_atendimento"
    db.refresh(c["consulta"])
    assert c["consulta"].atendimento_inicio == Relogio.atual
    ultimo = (
        db.query(HistoricoStatus)
        .filter_by(consulta_id=c["consulta"].id)
        .order_by(HistoricoStatus.id.desc())
        .first()
    )
    assert (ultimo.para_status, ultimo.usuario_id) == ("em_atendimento", c["prof_usuario"].id)


def test_chamar_sem_check_in_devolve_422(client, c):
    assert chamar(client, c["consulta"].id, c["prof_usuario"]).status_code == 422


def test_chamar_duas_vezes_devolve_422(client, c):
    preparar_confirmada(client, c)
    assert chamar(client, c["consulta"].id, c["prof_usuario"]).status_code == 200
    assert chamar(client, c["consulta"].id, c["prof_usuario"]).status_code == 422


def test_outro_profissional_e_recepcao_nao_podem_chamar(client, db, c):
    preparar_confirmada(client, c)
    outro = criar_usuario(db, "profissional", nome="Dr. Outro")
    assert chamar(client, c["consulta"].id, outro).status_code == 403
    assert chamar(client, c["consulta"].id, c["recepcao"]).status_code == 403
    assert chamar(client, c["consulta"].id, c["paciente"]).status_code == 403


# ---------- finalizar com anotação ----------

def finalizar(client, consulta_id, usuario, anotacao):
    return client.post(f"/api/consultas/{consulta_id}/finalizar",
                       json={"anotacao": anotacao}, headers=auth(usuario))


def preparar_em_atendimento(client, c):
    preparar_confirmada(client, c)
    assert chamar(client, c["consulta"].id, c["prof_usuario"]).status_code == 200


def test_finalizar_salva_anotacao_e_registra_fim(client, db, c):
    preparar_em_atendimento(client, c)
    r = finalizar(client, c["consulta"].id, c["prof_usuario"], "  Paciente com boa evolução.  ")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "realizada"
    db.refresh(c["consulta"])
    assert c["consulta"].anotacao == "Paciente com boa evolução."
    assert c["consulta"].atendimento_fim == Relogio.atual


def test_finalizar_sem_anotacao_devolve_422_e_nao_muda_o_status(client, db, c):
    preparar_em_atendimento(client, c)
    r = finalizar(client, c["consulta"].id, c["prof_usuario"], "   ")
    assert r.status_code == 422
    db.refresh(c["consulta"])
    assert c["consulta"].status == "em_atendimento" and c["consulta"].anotacao is None


def test_finalizar_com_anotacao_acima_de_5000_devolve_422(client, db, c):
    preparar_em_atendimento(client, c)
    r = finalizar(client, c["consulta"].id, c["prof_usuario"], "x" * 5001)
    assert r.status_code == 422
    db.refresh(c["consulta"])
    assert c["consulta"].status == "em_atendimento" and c["consulta"].anotacao is None


def test_finalizar_no_limite_de_5000_passa(client, c):
    preparar_em_atendimento(client, c)
    assert finalizar(client, c["consulta"].id, c["prof_usuario"], "x" * 5000).status_code == 200


def test_finalizar_sem_chamar_devolve_422(client, c):
    preparar_confirmada(client, c)
    assert finalizar(client, c["consulta"].id, c["prof_usuario"], "Anotação.").status_code == 422


def test_outros_perfis_nao_finalizam(client, db, c):
    preparar_em_atendimento(client, c)
    outro = criar_usuario(db, "profissional", nome="Dr. Outro")
    for usuario in (outro, c["recepcao"], c["paciente"]):
        assert finalizar(client, c["consulta"].id, usuario, "Anotação.").status_code == 403
