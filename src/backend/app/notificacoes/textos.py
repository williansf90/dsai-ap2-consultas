"""Textos das notificações, em português, com variáveis.

Nenhum texto de mensagem fica no meio da regra de negócio: tudo vive aqui.
Valores `datetime` são exibidos em America/Sao_Paulo.
"""
from datetime import datetime

from app.core.erros import RegraViolada
from app.core.tempo import FUSO_LOCAL

MODELOS = {
    "consulta_marcada": {
        "titulo": "Consulta marcada",
        "texto": "Sua consulta com {profissional} ({tipo_consulta}) foi marcada para {data_hora}, na unidade {unidade}.",
    },
    "consulta_remarcada": {
        "titulo": "Consulta remarcada",
        "texto": "Sua consulta com {profissional} foi remarcada: de {data_hora_antiga} para {data_hora}, na unidade {unidade}.",
    },
    "consulta_cancelada": {
        "titulo": "Consulta cancelada",
        "texto": "Sua consulta com {profissional} em {data_hora} foi cancelada pela clínica. Acesse Minhas consultas para remarcar.",
    },
}


def _formatar_data_hora(dt: datetime) -> str:
    return dt.astimezone(FUSO_LOCAL).strftime("%d/%m/%Y às %H:%M")


def renderizar(tipo: str, variaveis: dict) -> tuple[str, str]:
    """Renderiza título e texto de uma notificação a partir das variáveis."""
    modelo = MODELOS.get(tipo)
    if modelo is None:
        raise RegraViolada(f"Tipo de notificação desconhecido: {tipo}.")
    dados = {
        chave: _formatar_data_hora(valor) if isinstance(valor, datetime) else valor
        for chave, valor in variaveis.items()
    }
    return modelo["titulo"].format(**dados), modelo["texto"].format(**dados)
