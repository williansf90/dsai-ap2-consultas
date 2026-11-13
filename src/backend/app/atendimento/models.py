from sqlalchemy import Column, ForeignKey, Table

from app.core.db import Base

# recepção vinculada a unidades: só vê e opera a fila das unidades vinculadas (admin: todas)
recepcao_unidade = Table(
    "recepcao_unidade",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("unidade_id", ForeignKey("unidades.id", ondelete="CASCADE"), primary_key=True),
)
