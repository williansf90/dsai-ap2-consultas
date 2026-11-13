"""Spec: notificações — textos, criação, integração com o agendamento e central."""
import pytest

from app.core.erros import RegraViolada
from app.core.tempo import Relogio
from app.notificacoes.models import Notificacao
from app.notificacoes.service import criar
from app.notificacoes.textos import renderizar
from apoio import (
    auth,
    criar_especialidade,
    criar_faixa,
    criar_profissional,
    criar_unidade,
    criar_usuario,
    local,
)

SEG = "2026-10-12"


@pytest.fixture
def c(db):
    """Agora = seg 05/10 08:00. Profissional atende seg 08:00–12:00 na Unidade Centro."""
    Relogio.atual = local("2026-10-05 08:00")
    centro = criar_unidade(db)
    esp = criar_especialidade(db, tipos=(("Consulta", 30, 25000),))
    prof = criar_profissional(db, especialidades=[esp], unidades=[centro])
    criar_faixa(db, prof, centro, 0)
    paciente = criar_usuario(db, nome="Maria Paciente")
    return {"prof": prof, "centro": centro, "tipo": esp.tipos[0], "paciente": paciente,
            "recepcao": criar_usuario(db, "recepcao")}


def pedido(c, inicio, **extra):
    return {"profissional_id": c["prof"].id, "unidade_id": c["centro"].id, "tipo_consulta_id": c["tipo"].id,
            "inicio": local(inicio).isoformat(), **extra}


def marcar(client, c, inicio, usuario=None, **extra):
    return client.post("/api/consultas", json=pedido(c, inicio, **extra), headers=auth(usuario or c["paciente"]))


# ---------- textos e criação (sem commit próprio) ----------

def test_texto_de_consulta_marcada_em_portugues():
    titulo, texto = renderizar("consulta_marcada", {
        "profissional": "Dr. João Souza", "tipo_consulta": "Consulta",
        "unidade": "Unidade Centro", "data_hora": local(f"{SEG} 09:00"),
    })
    assert titulo == "Consulta marcada"
    assert "Dr. João Souza" in texto and "Consulta" in texto
    assert "12/10/2026 às 09:00" in texto and "Unidade Centro" in texto


def test_texto_de_remarcada_traz_data_antiga_e_nova():
    _, texto = renderizar("consulta_remarcada", {
        "profissional": "Dr. João Souza", "unidade": "Unidade Centro",
        "data_hora": local(f"{SEG} 10:00"), "data_hora_antiga": local(f"{SEG} 09:00"),
    })
    assert "de 12/10/2026 às 09:00 para 12/10/2026 às 10:00" in texto


def test_texto_de_cancelada_pela_clinica():
    titulo, texto = renderizar("consulta_cancelada", {
        "profissional": "Dr. João Souza", "data_hora": local(f"{SEG} 09:00"),
    })
    assert titulo == "Consulta cancelada"
    assert "cancelada pela clínica" in texto


def test_tipo_desconhecido_e_recusado():
    with pytest.raises(RegraViolada):
        renderizar("tipo_inexistente", {})


def test_criar_nao_faz_commit(db, c):
    notificacao = criar(db, c["paciente"].id, "consulta_marcada",
                        variaveis={"profissional": "Dr. João Souza", "tipo_consulta": "Consulta",
                                   "unidade": "Unidade Centro", "data_hora": local(f"{SEG} 09:00")})
    assert notificacao.id is None
    assert db.query(Notificacao).count() == 0  # sem commit próprio: só existe após a transação fechar
    db.commit()
    assert db.query(Notificacao).count() == 1


# ---------- notificação ao marcar ----------

def criar_paciente(c):
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        return criar_usuario(s, nome="Outro Paciente")


def test_marcar_pelo_paciente_cria_notificacao(client, db, c):
    r = marcar(client, c, f"{SEG} 09:00")
    assert r.status_code == 201, r.text
    n = db.query(Notificacao).one()
    assert n.usuario_id == c["paciente"].id
    assert n.tipo == "consulta_marcada" and n.lida_em is None
    assert n.consulta_id == r.json()["id"]
    assert "Dr. João Souza" in n.texto and "12/10/2026 às 09:00" in n.texto


def test_marcar_pela_recepcao_notifica_o_paciente(client, db, c):
    r = marcar(client, c, f"{SEG} 09:00", usuario=c["recepcao"], paciente_id=c["paciente"].id)
    assert r.status_code == 201, r.text
    n = db.query(Notificacao).one()
    assert n.usuario_id == c["paciente"].id  # destinatário é o paciente, não a recepção


def test_marcar_para_horario_ocupado_nao_cria_notificacao(client, db, c):
    assert marcar(client, c, f"{SEG} 09:00").status_code == 201
    outro = criar_paciente(c)
    assert marcar(client, c, f"{SEG} 09:00", usuario=c["recepcao"], paciente_id=outro.id).status_code == 409
    assert db.query(Notificacao).count() == 1  # só a notificação da primeira marcação


# ---------- notificação ao remarcar (atomicidade) ----------

def remarcar(client, c, consulta_id, inicio, usuario=None):
    return client.post(f"/api/consultas/{consulta_id}/remarcar",
                       json={"inicio": local(inicio).isoformat()},
                       headers=auth(usuario or c["paciente"]))


def test_remarcar_cria_notificacao_com_data_antiga_e_nova(client, db, c):
    consulta_id = marcar(client, c, f"{SEG} 09:00").json()["id"]
    r = remarcar(client, c, consulta_id, f"{SEG} 10:00")
    assert r.status_code == 201, r.text
    n = db.query(Notificacao).filter_by(tipo="consulta_remarcada").one()
    assert n.usuario_id == c["paciente"].id and n.consulta_id == r.json()["id"]
    assert "de 12/10/2026 às 09:00 para 12/10/2026 às 10:00" in n.texto


def test_remarcar_pela_recepcao_tambem_notifica_o_paciente(client, db, c):
    consulta_id = marcar(client, c, f"{SEG} 09:00").json()["id"]
    assert remarcar(client, c, consulta_id, f"{SEG} 10:00", usuario=c["recepcao"]).status_code == 201
    n = db.query(Notificacao).filter_by(tipo="consulta_remarcada").one()
    assert n.usuario_id == c["paciente"].id


def test_remarcar_para_horario_ocupado_nao_deixa_notificacao(client, db, c):
    consulta_id = marcar(client, c, f"{SEG} 09:00").json()["id"]
    outro = criar_paciente(c)
    assert marcar(client, c, f"{SEG} 10:00", usuario=c["recepcao"], paciente_id=outro.id).status_code == 201
    r = remarcar(client, c, consulta_id, f"{SEG} 10:00")
    assert r.status_code == 409
    assert db.query(Notificacao).filter_by(tipo="consulta_remarcada").count() == 0  # rollback remove a notificação


# ---------- notificação ao cancelar pela clínica ----------

def cancelar(client, c, consulta_id, usuario=None):
    return client.post(f"/api/consultas/{consulta_id}/cancelar", headers=auth(usuario or c["paciente"]))


def test_cancelamento_pela_recepcao_notifica_o_paciente(client, db, c):
    consulta_id = marcar(client, c, f"{SEG} 09:00").json()["id"]
    r = cancelar(client, c, consulta_id, usuario=c["recepcao"])
    assert r.status_code == 200 and r.json()["status"] == "cancelada_clinica"
    n = db.query(Notificacao).filter_by(tipo="consulta_cancelada").one()
    assert n.usuario_id == c["paciente"].id and n.consulta_id == consulta_id
    assert "cancelada pela clínica" in n.texto


def test_cancelamento_pelo_paciente_nao_cria_notificacao(client, db, c):
    consulta_id = marcar(client, c, f"{SEG} 09:00").json()["id"]
    r = cancelar(client, c, consulta_id)
    assert r.status_code == 200 and r.json()["status"] == "cancelada_paciente"
    assert db.query(Notificacao).filter_by(tipo="consulta_cancelada").count() == 0


def test_cancelar_consulta_ja_cancelada_nao_cria_notificacao(client, db, c):
    consulta_id = marcar(client, c, f"{SEG} 09:00").json()["id"]
    assert cancelar(client, c, consulta_id).status_code == 200
    assert cancelar(client, c, consulta_id, usuario=c["recepcao"]).status_code == 422
    assert db.query(Notificacao).filter_by(tipo="consulta_cancelada").count() == 0


# ---------- central: listar, marcar lida, marcar todas ----------

def criar_notificacao(db, usuario_id, texto_extra=""):
    return criar(db, usuario_id, "consulta_marcada", variaveis={
        "profissional": "Dr. João Souza", "tipo_consulta": "Consulta",
        "unidade": "Unidade Centro", "data_hora": local(f"{SEG} 09:00"),
    })


def test_lista_so_as_proprias_e_conta_nao_lidas(client, db, c):
    marcar(client, c, f"{SEG} 09:00")
    marcar(client, c, f"{SEG} 10:00")
    criar_notificacao(db, criar_paciente(c).id)  # de outro usuário
    db.commit()
    r = client.get("/api/notificacoes", headers=auth(c["paciente"]))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 2 and corpo["nao_lidas"] == 2  # privacidade: as do outro não aparecem
    assert all("usuario_id" not in n for n in corpo["itens"])  # não expõe destinatário
    assert corpo["itens"][0]["id"] > corpo["itens"][1]["id"]  # mais recentes primeiro
    assert all(n["lida_em"] is None for n in corpo["itens"])


def test_paginacao_da_lista(client, db, c):
    for _ in range(25):
        criar_notificacao(db, c["paciente"].id)
    db.commit()
    r = client.get("/api/notificacoes?pagina=2&por_pagina=10", headers=auth(c["paciente"]))
    corpo = r.json()
    assert (corpo["total"], corpo["pagina"], corpo["paginas"]) == (25, 2, 3)
    assert len(corpo["itens"]) == 10


def test_marcar_lida_propria(client, db, c):
    marcar(client, c, f"{SEG} 09:00")
    n = db.query(Notificacao).one()
    r = client.patch(f"/api/notificacoes/{n.id}/lida", headers=auth(c["paciente"]))
    assert r.status_code == 200 and r.json()["lida_em"] is not None
    assert client.get("/api/notificacoes", headers=auth(c["paciente"])).json()["nao_lidas"] == 0


def test_marcar_lida_de_outro_usuario_devolve_404(client, db, c):
    marcar(client, c, f"{SEG} 09:00")
    n = db.query(Notificacao).one()
    r = client.patch(f"/api/notificacoes/{n.id}/lida", headers=auth(criar_paciente(c)))
    assert r.status_code == 404
    db.refresh(n)
    assert n.lida_em is None


def test_marcar_todas_lidas(client, db, c):
    marcar(client, c, f"{SEG} 09:00")
    marcar(client, c, f"{SEG} 10:00")
    r = client.post("/api/notificacoes/marcar-todas-lidas", headers=auth(c["paciente"]))
    assert r.status_code == 200 and r.json() == {"atualizadas": 2}
    assert client.get("/api/notificacoes", headers=auth(c["paciente"])).json()["nao_lidas"] == 0
    r2 = client.post("/api/notificacoes/marcar-todas-lidas", headers=auth(c["paciente"]))
    assert r2.json() == {"atualizadas": 0}


def test_sem_token_devolve_401(client):
    assert client.get("/api/notificacoes").status_code == 401
    assert client.patch("/api/notificacoes/1/lida").status_code == 401
    assert client.post("/api/notificacoes/marcar-todas-lidas").status_code == 401
