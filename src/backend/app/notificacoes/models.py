from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# tipos aceitos nesta fase; novos tipos (lembretes, lista de espera...) exigem migração do CHECK
TIPOS = (
    "consulta_marcada",
    "consulta_remarcada",
    "consulta_cancelada",
)


class Notificacao(Base):
    __tablename__ = "notificacoes"
    __table_args__ = (
        CheckConstraint(f"tipo IN {TIPOS}", name="ck_notificacoes_tipo"),
        Index("ix_notificacoes_usuario_criado_em", "usuario_id", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(30))
    titulo: Mapped[str] = mapped_column(String(120))
    texto: Mapped[str] = mapped_column(String(500))
    consulta_id: Mapped[int | None] = mapped_column(ForeignKey("consultas.id", ondelete="SET NULL"), index=True)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
