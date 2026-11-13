from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: str
    titulo: str
    texto: str
    consulta_id: int | None
    lida_em: datetime | None
    criado_em: datetime


class ListaNotificacoes(BaseModel):
    itens: list[NotificacaoOut]
    total: int
    pagina: int
    paginas: int
    nao_lidas: int
