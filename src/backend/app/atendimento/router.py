from datetime import date

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.agendamento.schemas import ConsultaOut, UnidadeRef
from app.agendamento.service import com_permissoes
from app.atendimento import service
from app.atendimento.schemas import AnotacaoOut, FilaItem, FinalizarIn, VinculoIn, VinculoRecepcao
from app.core.db import get_db
from app.core.seguranca import exige_perfil, usuario_atual

router = APIRouter(tags=["atendimento"])
quem_faz_check_in = exige_perfil("paciente", "recepcao", "admin")
equipe = exige_perfil("recepcao", "admin")
so_admin = exige_perfil("admin")
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


# ---------- fila do dia ----------

@router.get("/fila", response_model=list[FilaItem])
def fila(unidade_id: int, data: date, usuario=Depends(equipe), db: Session = Depends(get_db)):
    return service.fila_do_dia(db, usuario, unidade_id, data)


@router.get("/fila/unidades", response_model=list[UnidadeRef])
def fila_unidades(usuario=Depends(equipe), db: Session = Depends(get_db)):
    return service.unidades_permitidas(db, usuario)


# ---------- vínculo recepção ↔ unidade (admin) ----------

@router.get("/recepcao-unidades", response_model=list[VinculoRecepcao])
def listar_vinculos(_=Depends(so_admin), db: Session = Depends(get_db)):
    return service.vinculos_recepcao(db)


@router.post("/recepcao-unidades", response_model=VinculoRecepcao, status_code=status.HTTP_201_CREATED)
def vincular(dados: VinculoIn, _=Depends(so_admin), db: Session = Depends(get_db)):
    return service.vincular(db, dados.usuario_id, dados.unidade_id)


@router.delete("/recepcao-unidades", status_code=status.HTTP_204_NO_CONTENT)
def desvincular(dados: VinculoIn, _=Depends(so_admin), db: Session = Depends(get_db)):
    service.desvincular(db, dados.usuario_id, dados.unidade_id)


# ---------- comprovante de comparecimento ----------

@router.get("/consultas/{consulta_id}/comprovante.pdf")
def comprovante(consulta_id: int, usuario=Depends(exige_perfil("paciente")), db: Session = Depends(get_db)):
    conteudo = service.comprovante(db, consulta_id, usuario)
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="comprovante-{consulta_id}.pdf"'},
    )
