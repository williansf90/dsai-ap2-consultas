"""Importa os modelos de todos os módulos para o Alembic e para os testes."""
from app.agenda import models as agenda_models  # noqa: F401
from app.agendamento import models as agendamento_models  # noqa: F401
from app.atendimento import models as atendimento_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.clinicas import models as clinicas_models  # noqa: F401
from app.notificacoes import models as notificacoes_models  # noqa: F401
from app.core.db import Base

__all__ = ["Base"]
