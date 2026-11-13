from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.agendamento.schemas import ConsultaOut


class FinalizarIn(BaseModel):
    anotacao: str


class AnotacaoOut(BaseModel):
    anotacao: str | None


class FilaItem(ConsultaOut):
    chegada_em: datetime | None
    pode_check_in: bool = False
    pode_faltou: bool = False


class RecepcaoRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    email: str


class VinculoRecepcao(BaseModel):
    usuario: RecepcaoRef
    unidade_ids: list[int]


class VinculoIn(BaseModel):
    usuario_id: int
    unidade_id: int
