"""Spec: exportação de consultas para calendário — regras de negócio e segurança."""
import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.agendamento import service
from app.core.erros import RegraViolada
from app.core.tempo import Relogio
from app.main import app
from apoio import auth, criar_consulta, criar_especialidade, criar_profissional, criar_unidade, criar_usuario, local


@pytest.fixture
def c(db):
    """Agora = seg 05/10/2026 08:00 (SP). Unidade Centro, tipo Consulta de 30 min, paciente Maria."""
    Relogio.atual = local("2026-10-05 08:00")
    centro = criar_unidade(db)
    esp = criar_especialidade(db, tipos=(("Consulta", 30, 25000),))
    prof = criar_profissional(db, especialidades=[esp], unidades=[centro])
    return {"prof": prof, "centro": centro, "tipo": esp.tipos[0],
            "paciente": criar_usuario(db, nome="Maria Paciente", cpf="52998224725")}


def exportar(client, usuario):
    return client.get("/api/consultas/minhas/exportar.ics", headers=auth(usuario))


def marcar(db, c, inicio, status="marcada", paciente=None):
    return criar_consulta(db, paciente or c["paciente"], c["prof"], c["centro"], c["tipo"],
                          local(inicio), status=status)


# ---------- acesso ----------

def test_sem_token_recebe_401(client):
    assert client.get("/api/consultas/minhas/exportar.ics").status_code == 401


@pytest.mark.parametrize("perfil", ["recepcao", "profissional", "admin"])
def test_perfil_nao_paciente_recebe_403(client, db, c, perfil):
    r = exportar(client, criar_usuario(db, perfil))
    assert r.status_code == 403
    assert r.json()["detail"] == "Seu perfil não tem permissão para esta ação."


# ---------- propriedade dos agendamentos ----------

def test_exporta_somente_consultas_do_paciente(client, db, c):
    marcar(db, c, "2026-10-12 09:00")                       # do paciente
    marcar(db, c, "2026-10-12 10:00", paciente=criar_usuario(db, nome="Outro Paciente"))
    r = exportar(client, c["paciente"])
    assert r.status_code == 200
    assert r.text.count("BEGIN:VEVENT") == 1
    assert "DTSTART:20261012T120000Z" in r.text       # 09:00 SP -> 12:00 UTC
    assert "DTSTART:20261012T130000Z" not in r.text   # 10:00 SP do outro paciente


# ---------- elegibilidade ----------

def test_consultas_passadas_nao_sao_exportadas(client, db, c):
    marcar(db, c, "2026-10-04 09:00")   # já passou
    marcar(db, c, "2026-10-05 08:00")   # início == agora (limite, RN04)
    marcar(db, c, "2026-10-12 09:00")   # futura
    r = exportar(client, c["paciente"])
    assert r.text.count("BEGIN:VEVENT") == 1
    assert "DTSTART:20261012T120000Z" in r.text


@pytest.mark.parametrize("status", ["cancelada_paciente", "cancelada_clinica", "faltou", "realizada", "em_atendimento"])
def test_status_nao_elegiveis_nao_sao_exportados(client, db, c, status):
    marcar(db, c, "2026-10-12 09:00", status=status)
    r = exportar(client, c["paciente"])
    assert "BEGIN:VEVENT" not in r.text


def test_marcadas_e_confirmadas_futuras_sao_exportadas_em_ordem(client, db, c):
    marcar(db, c, "2026-10-12 10:00", status="confirmada")
    marcar(db, c, "2026-10-12 09:00", status="marcada")
    texto = exportar(client, c["paciente"]).text
    assert texto.count("BEGIN:VEVENT") == 2
    assert texto.index("DTSTART:20261012T120000Z") < texto.index("DTSTART:20261012T130000Z")


# ---------- formato do arquivo ----------

def test_datas_duracao_e_dtstamp_em_utc(client, db, c):
    marcar(db, c, "2026-10-12 09:00")
    texto = exportar(client, c["paciente"]).text
    assert "DTSTART:20261012T120000Z" in texto          # 09:00 SP -> 12:00 UTC
    assert "DTEND:20261012T123000Z" in texto            # duração de 30 min
    assert "DTSTAMP:20261005T110000Z" in texto          # agora (08:00 SP -> 11:00 UTC)


def test_caracteres_especiais_e_acentuacao(client, db, c):
    prof = criar_profissional(db, "Dr. João; Souza, Neto")
    unidade = criar_unidade(db, nome="Unidade São\nJoão; Centro")
    unidade.endereco = "Rua Antônio, 1234; sala 2, bloco B, próximo à praça São João, bairro Centro, cidade Belém do Pará"
    db.add(unidade)
    db.commit()
    criar_consulta(db, c["paciente"], prof, unidade, c["tipo"], local("2026-10-12 09:00"))
    texto = exportar(client, c["paciente"]).text
    assert "Dr. João\\; Souza\\, Neto" in texto
    assert "Unidade São\\nJoão\\; Centro" in texto
    assert "Rua Antônio\\, 1234\\; sala 2" in texto
    assert "\r\n" in texto and re.search(r"(?<!\r)\n", texto) is None  # CRLF em todas as linhas
    linhas = [linha for linha in texto.split("\r\n") if linha]
    assert all(len(linha.encode("utf-8")) <= 75 for linha in linhas)  # dobra em 75 octetos
    assert any(linha.startswith(" ") for linha in linhas)             # houve dobra de linha


def test_cabecalhos_de_download(client, db, c):
    marcar(db, c, "2026-10-12 09:00")
    r = exportar(client, c["paciente"])
    assert r.headers["content-type"] == "text/calendar; charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="consultas.ics"'


def test_sem_consultas_gera_calendario_vazio_valido(client, db, c):
    r = exportar(client, c["paciente"])
    assert r.status_code == 200
    texto = r.text
    assert "BEGIN:VCALENDAR" in texto and "END:VCALENDAR" in texto
    assert "VERSION:2.0" in texto
    assert "PRODID:-//MarcaConsulta//Consultas//PT-BR" in texto
    assert "CALSCALE:GREGORIAN" in texto
    assert "BEGIN:VEVENT" not in texto


def test_uid_estavel_e_distinto(client, db, c):
    marcar(db, c, "2026-10-12 09:00")
    marcar(db, c, "2026-10-13 09:00")
    uids1 = re.findall(r"UID:(\S+)", exportar(client, c["paciente"]).text)
    uids2 = re.findall(r"UID:(\S+)", exportar(client, c["paciente"]).text)
    assert uids1 == uids2                 # estável entre exportações
    assert len(set(uids1)) == 2           # distinto por consulta


# ---------- privacidade e consistência ----------

def test_dados_sensiveis_ausentes(client, db, c):
    marcar(db, c, "2026-10-12 09:00")
    texto = exportar(client, c["paciente"]).text
    assert "Maria" not in texto           # nome do paciente
    assert "52998224725" not in texto     # CPF do paciente
    assert "SUMMARY:Consulta médica" in texto


def test_horario_sem_fuso_gera_erro_explicito():
    from types import SimpleNamespace

    consulta = SimpleNamespace(
        id=1, inicio=datetime(2026, 10, 12, 9, 0), fim=datetime(2026, 10, 12, 9, 30),
        profissional=SimpleNamespace(nome="Dr. X"), unidade=SimpleNamespace(nome="U", endereco=""),
    )
    with pytest.raises(RegraViolada, match="fuso"):
        service.gerar_ical([consulta])


def test_rota_aparece_na_varredura_de_rotas_protegidas():
    for rota in app.routes:
        if getattr(rota, "path", "") == "/api/consultas/minhas/exportar.ics":
            break
    else:
        pytest.fail("rota de exportação não registrada")
