"""Comprovante de comparecimento em PDF (ReportLab). Não inclui a anotação clínica."""
from datetime import datetime
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.agendamento.models import Consulta
from app.core.tempo import FUSO_LOCAL, agora_utc

COR_TITULO = "#0b6e4f"
COR_TEXTO = "#1f2933"


def _data_hora_local(dt: datetime) -> str:
    return dt.astimezone(FUSO_LOCAL).strftime("%d/%m/%Y às %H:%M")


def gerar_comprovante(consulta: Consulta) -> bytes:
    """PDF com os dados de comparecimento, no fuso local, sem a anotação clínica."""
    buffer = BytesIO()
    # sem compressão: o conteúdo fica legível no arquivo (e verificável nos testes)
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
    largura, altura = A4
    pdf.setTitle("Comprovante de comparecimento")

    y = altura - 64
    pdf.setFillColor(COR_TITULO)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(48, y, "MarcaConsulta")
    y -= 22
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(48, y, "Comprovante de comparecimento")
    y -= 36

    pdf.setFillColor(COR_TEXTO)
    linhas = [
        ("Paciente", consulta.paciente.nome),
        ("Profissional", f"{consulta.profissional.nome} ({consulta.profissional.registro})"),
        ("Unidade", f"{consulta.unidade.nome} — {consulta.unidade.endereco}"),
        ("Tipo de consulta", consulta.tipo_consulta.nome),
        ("Data e hora", _data_hora_local(consulta.inicio)),
        ("Realizado em", _data_hora_local(consulta.atendimento_fim) if consulta.atendimento_fim else "—"),
    ]
    for rotulo, valor in linhas:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(48, y, f"{rotulo}:")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(190, y, valor)
        y -= 24

    y -= 24
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor("#5f6b7a")
    pdf.drawString(48, y, f"Emitido em {_data_hora_local(agora_utc())}. Documento sem valor fiscal.")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
