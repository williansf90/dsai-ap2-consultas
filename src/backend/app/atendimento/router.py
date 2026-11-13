from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agendamento.schemas import ConsultaOut
from app.agendamento.service import com_permissoes
from app.atendimento import service
from app.atendimento.schemas import AnotacaoOut, FinalizarIn
from app.core.db import get_db
from app.core.seguranca import exige_perfil, usuario_atual

router = APIRouter(tags=["atendimento"])
quem_faz_check_in = exige_perfil("paciente", "recepcao", "admin")
equipe = exige_perfil("recepcao", "admin")
profissional = exige_perfil("profissional")


@router.post("/consultas/{consulta_id}/check-in", response_model=ConsultaOut)
def check_in(consulta_id: int, usuario=Depends(quem_faz_check_in), db: Session = Depends(get_db)):
    consulta = service.check_in(db, consulta_id, usuario)
    return com_permissoes(consulta, usuario)


@router.post("/consultas/{consulta_id}/chamar", response_model=ConsultaOut)
def chamar(consulta_id: int, usuario=Depends(profissional), db: Session = Depends(get_db)):
    consulta = service.chamar(db, consulta_id, usuario)
    return com_permissoes(consulta, usuario)


@router.post("/consultas/{consulta_id}/finalizar", response_model=ConsultaOut)
def finalizar(consulta_id: int, dados: FinalizarIn, usuario=Depends(profissional), db: Session = Depends(get_db)):
    consulta = service.finalizar(db, consulta_id, usuario, dados.anotacao)
    return com_permissoes(consulta, usuario)


@router.get("/consultas/{consulta_id}/anotacao", response_model=AnotacaoOut)
def anotacao(consulta_id: int, usuario=Depends(usuario_atual), db: Session = Depends(get_db)):
    return {"anotacao": service.anotacao(db, consulta_id, usuario)}


@router.post("/consultas/{consulta_id}/faltou", response_model=ConsultaOut)
def faltou(consulta_id: int, usuario=Depends(equipe), db: Session = Depends(get_db)):
    consulta = service.marcar_faltou(db, consulta_id, usuario)
    return com_permissoes(consulta, usuario)
