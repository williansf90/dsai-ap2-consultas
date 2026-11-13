from pydantic import BaseModel


class FinalizarIn(BaseModel):
    anotacao: str


class AnotacaoOut(BaseModel):
    anotacao: str | None
