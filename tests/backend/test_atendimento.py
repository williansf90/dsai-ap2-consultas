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


# ---------- visibilidade da anotação ----------

def marcar_realizada_com_anotacao(db, c, anotacao="Evolução boa."):
    c["consulta"].status = "realizada"
    c["consulta"].anotacao = anotacao
    db.commit()


def ver_anotacao(client, consulta_id, usuario):
    return client.get(f"/api/consultas/{consulta_id}/anotacao", headers=auth(usuario))


def test_autor_da_consulta_ve_a_anotacao(client, db, c):
    marcar_realizada_com_anotacao(db, c)
    r = ver_anotacao(client, c["consulta"].id, c["prof_usuario"])
    assert r.status_code == 200 and r.json() == {"anotacao": "Evolução boa."}


def test_profissional_da_mesma_especialidade_ve_a_anotacao(client, db, c):
    marcar_realizada_com_anotacao(db, c)
    colega = criar_usuario(db, "profissional", nome="Dra. Colega")
    criar_profissional(db, nome="Dra. Colega", especialidades=[c["esp"]], unidades=[c["centro"]], usuario=colega)
    r = ver_anotacao(client, c["consulta"].id, colega)
    assert r.status_code == 200 and r.json() == {"anotacao": "Evolução boa."}


def test_profissional_de_outra_especialidade_nao_ve_a_anotacao(client, db, c):
    marcar_realizada_com_anotacao(db, c)
    outra = criar_especialidade(db, nome="Dermatologia", tipos=(("Avaliação", 30, 20000),))
    outro = criar_usuario(db, "profissional", nome="Dr. Outro")
    criar_profissional(db, nome="Dr. Outro", especialidades=[outra], unidades=[c["centro"]], usuario=outro)
    assert ver_anotacao(client, c["consulta"].id, outro).status_code == 403


@pytest.mark.parametrize("perfil", ["paciente", "recepcao", "admin"])
def test_paciente_recepcao_e_admin_nao_veem_a_anotacao(client, db, c, perfil):
    marcar_realizada_com_anotacao(db, c)
    assert ver_anotacao(client, c["consulta"].id, c[perfil]).status_code == 403


def test_anotacao_de_consulta_inexistente_devolve_404(client, c):
    assert ver_anotacao(client, 999999, c["prof_usuario"]).status_code == 404


# ---------- faltou manual ----------

def marcar_faltou(client, consulta_id, usuario):
    return client.post(f"/api/consultas/{consulta_id}/faltou", headers=auth(usuario))


def test_faltou_antes_de_30_minutos_devolve_422(client, c):
    Relogio.atual = local(f"{SEG} 09:00")  # no horário exato, antes dos 30 min
    assert marcar_faltou(client, c["consulta"].id, c["recepcao"]).status_code == 422


def test_faltou_apos_30_minutos_funciona(client, db, c):
    Relogio.atual = local(f"{SEG} 09:31")
    r = marcar_faltou(client, c["consulta"].id, c["recepcao"])
    assert r.status_code == 200 and r.json()["status"] == "faltou"
    ultimo = (
        db.query(HistoricoStatus)
        .filter_by(consulta_id=c["consulta"].id)
        .order_by(HistoricoStatus.id.desc())
        .first()
    )
    assert (ultimo.para_status, ultimo.usuario_id) == ("faltou", c["recepcao"].id)


def test_faltou_duplicado_devolve_422(client, c):
    Relogio.atual = local(f"{SEG} 09:31")
    assert marcar_faltou(client, c["consulta"].id, c["recepcao"]).status_code == 200
    assert marcar_faltou(client, c["consulta"].id, c["recepcao"]).status_code == 422


def test_paciente_e_profissional_nao_marcam_faltou(client, c):
    Relogio.atual = local(f"{SEG} 09:31")
    assert marcar_faltou(client, c["consulta"].id, c["paciente"]).status_code == 403
    assert marcar_faltou(client, c["consulta"].id, c["prof_usuario"]).status_code == 403


def test_faltou_de_consulta_cancelada_devolve_422(client, c):
    Relogio.atual = local(f"{SEG} 09:31")
    assert client.post(f"/api/consultas/{c['consulta'].id}/cancelar", headers=auth(c["recepcao"])).status_code == 200
    assert marcar_faltou(client, c["consulta"].id, c["recepcao"]).status_code == 422


# ---------- fila do dia ----------

def vincular_recepcao(db, usuario, unidade):
    from app.atendimento.models import recepcao_unidade

    db.execute(recepcao_unidade.insert().values(usuario_id=usuario.id, unidade_id=unidade.id))
    db.commit()


def pedido_fila(client, unidade_id, dia, usuario):
    return client.get(f"/api/fila?unidade_id={unidade_id}&data={dia}", headers=auth(usuario))


def test_fila_ordenada_por_horario_com_flags(client, db, c):
    vincular_recepcao(db, c["recepcao"], c["centro"])
    outro = criar_usuario(db, nome="Outro Paciente")
    criar_consulta(db, outro, c["prof"], c["centro"], c["tipo"], local(f"{SEG} 10:00"))
    Relogio.atual = local(f"{SEG} 08:00")
    r = pedido_fila(client, c["centro"].id, SEG, c["recepcao"])
    assert r.status_code == 200
    itens = r.json()
    assert [i["paciente"]["nome"] for i in itens] == ["Maria Paciente", "Outro Paciente"]
    assert (itens[0]["pode_check_in"], itens[0]["pode_faltou"]) == (True, False)  # 09:00, agora 08:00
    assert (itens[1]["pode_check_in"], itens[1]["pode_faltou"]) == (False, False)  # 10:00: falta mais de 1h
    assert all(i["chegada_em"] is None for i in itens)


def test_fila_flag_de_faltou_apos_30_minutos(client, db, c):
    vincular_recepcao(db, c["recepcao"], c["centro"])
    Relogio.atual = local(f"{SEG} 09:31")
    itens = pedido_fila(client, c["centro"].id, SEG, c["recepcao"]).json()
    assert itens[0]["pode_faltou"] is True and itens[0]["pode_check_in"] is True


def test_fila_mostra_chegada_e_status_apos_check_in(client, db, c):
    vincular_recepcao(db, c["recepcao"], c["centro"])
    Relogio.atual = local(f"{SEG} 08:30")
    assert check_in(client, c["consulta"].id, c["paciente"]).status_code == 200
    itens = pedido_fila(client, c["centro"].id, SEG, c["recepcao"]).json()
    assert itens[0]["status"] == "confirmada" and itens[0]["chegada_em"] is not None
    assert itens[0]["pode_check_in"] is False


def test_fila_de_outro_dia_nao_traz_consultas(client, db, c):
    vincular_recepcao(db, c["recepcao"], c["centro"])
    assert pedido_fila(client, c["centro"].id, "2026-10-13", c["recepcao"]).json() == []


def test_recepcao_sem_vinculo_nao_ve_a_fila(client, c):
    assert pedido_fila(client, c["centro"].id, SEG, c["recepcao"]).status_code == 403


def test_recepcao_vinculada_so_a_outra_unidade_nao_ve_a_fila(client, db, c):
    outra_unidade = criar_unidade(db, nome="Unidade Sul")
    vincular_recepcao(db, c["recepcao"], outra_unidade)
    assert pedido_fila(client, c["centro"].id, SEG, c["recepcao"]).status_code == 403


def test_admin_ve_a_fila_de_qualquer_unidade(client, c):
    assert pedido_fila(client, c["centro"].id, SEG, c["admin"]).status_code == 200


def test_unidade_inexistente_na_fila_devolve_404(client, c):
    assert pedido_fila(client, 999999, SEG, c["admin"]).status_code == 404


def test_paciente_nao_ve_a_fila(client, c):
    assert pedido_fila(client, c["centro"].id, SEG, c["paciente"]).status_code == 403


def test_fila_unidades_respeita_o_vinculo(client, db, c):
    outra_unidade = criar_unidade(db, nome="Unidade Sul")
    vincular_recepcao(db, c["recepcao"], c["centro"])
    r = client.get("/api/fila/unidades", headers=auth(c["recepcao"]))
    assert [u["id"] for u in r.json()] == [c["centro"].id]
    r2 = client.get("/api/fila/unidades", headers=auth(c["admin"]))
    assert {u["id"] for u in r2.json()} == {c["centro"].id, outra_unidade.id}


# ---------- vínculo recepção ↔ unidade (admin) ----------

def test_vinculo_e_desvinculo_somente_admin(client, db, c):
    corpo = {"usuario_id": c["recepcao"].id, "unidade_id": c["centro"].id}
    assert client.post("/api/recepcao-unidades", json=corpo, headers=auth(c["recepcao"])).status_code == 403
    r = client.post("/api/recepcao-unidades", json=corpo, headers=auth(c["admin"]))
    assert r.status_code == 201 and r.json()["unidade_ids"] == [c["centro"].id]
    assert client.get("/api/recepcao-unidades", headers=auth(c["admin"])).json()[0]["unidade_ids"] == [c["centro"].id]
    # vínculo duplicado é idempotente
    assert client.post("/api/recepcao-unidades", json=corpo, headers=auth(c["admin"])).status_code == 201
    assert client.request("DELETE", "/api/recepcao-unidades", json=corpo, headers=auth(c["admin"])).status_code == 204
    assert client.get("/api/recepcao-unidades", headers=auth(c["admin"])).json()[0]["unidade_ids"] == []
    assert client.request("DELETE", "/api/recepcao-unidades", json=corpo, headers=auth(c["admin"])).status_code == 404


def test_vinculo_de_usuario_que_nao_e_recepcao_devolve_404(client, c):
    r = client.post("/api/recepcao-unidades",
                    json={"usuario_id": c["paciente"].id, "unidade_id": c["centro"].id},
                    headers=auth(c["admin"]))
    assert r.status_code == 404


def test_vinculo_de_unidade_inativa_devolve_404(client, db, c):
    c["centro"].ativa = False
    db.commit()
    r = client.post("/api/recepcao-unidades",
                    json={"usuario_id": c["recepcao"].id, "unidade_id": c["centro"].id},
                    headers=auth(c["admin"]))
    assert r.status_code == 404


# ---------- comprovante de comparecimento (PDF) ----------

def baixar_comprovante(client, consulta_id, usuario):
    return client.get(f"/api/consultas/{consulta_id}/comprovante.pdf", headers=auth(usuario))


def test_comprovante_de_consulta_realizada_sem_anotacao(client, db, c):
    preparar_em_atendimento(client, c)
    assert finalizar(client, c["consulta"].id, c["prof_usuario"], "Evolução boa.").status_code == 200
    r = baixar_comprovante(client, c["consulta"].id, c["paciente"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    conteudo = r.content
    assert conteudo.startswith(b"%PDF")
    assert b"Maria Paciente" in conteudo
    assert b"Dr. Jo" in conteudo  # "João" tem acento; o prefixo ASCII basta
    assert b"Unidade Centro" in conteudo
    assert b"12/10/2026" in conteudo  # data no fuso de São Paulo
    assert b"Evolu" not in conteudo  # decisão 10: a anotação não aparece no comprovante


def test_comprovante_de_consulta_nao_realizada_devolve_422(client, c):
    r = baixar_comprovante(client, c["consulta"].id, c["paciente"])
    assert r.status_code == 422
    assert "realizadas" in r.json()["detail"]


def test_comprovante_de_outro_paciente_devolve_404(client, db, c):
    preparar_em_atendimento(client, c)
    assert finalizar(client, c["consulta"].id, c["prof_usuario"], "Evolução boa.").status_code == 200
    intruso = criar_usuario(db, nome="Intruso")
    assert baixar_comprovante(client, c["consulta"].id, intruso).status_code == 404


def test_comprovante_exige_login(client, c):
    assert client.get(f"/api/consultas/{c['consulta'].id}/comprovante.pdf").status_code == 401


def test_comprovante_de_recepcao_devolve_403(client, db, c):
    preparar_em_atendimento(client, c)
    assert finalizar(client, c["consulta"].id, c["prof_usuario"], "Evolução boa.").status_code == 200
    assert baixar_comprovante(client, c["consulta"].id, c["recepcao"]).status_code == 403
