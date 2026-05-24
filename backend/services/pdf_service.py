"""PDF generation for diários de obra using reportlab."""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any


def gerar_pdf_diario(diario: dict, registros: list[dict]) -> bytes:
    """Generate a PDF for a diário de obra. Returns raw PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=14, spaceAfter=6)
    sub_style = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    label_style = ParagraphStyle("label", parent=styles["Normal"], fontSize=10, spaceAfter=2)

    obra_nome = diario.get("obra_nome") or f"Obra {diario.get('obra_id', '')}"
    tipo = diario.get("tipo", "diario").capitalize()
    data_inicio = diario.get("data_inicio", "")
    data_fim = diario.get("data_fim", "")
    versao = diario.get("versao_atual", 1)
    status = diario.get("status", "rascunho").capitalize()
    tenant_nome = diario.get("tenant_nome", "")
    gerado_por_nome = diario.get("gerado_por_nome", "")
    gerado_em = diario.get("gerado_em") or datetime.now().strftime("%d/%m/%Y %H:%M")

    periodo = (
        f"{_fmt_date(data_inicio)}" if data_inicio == data_fim
        else f"{_fmt_date(data_inicio)} a {_fmt_date(data_fim)}"
    )

    story: list[Any] = []

    story.append(Paragraph(f"Diário de Obra — {tipo}", title_style))
    story.append(Paragraph(obra_nome, ParagraphStyle("obra", parent=styles["Heading2"], fontSize=12, spaceAfter=4)))
    story.append(Paragraph(f"Período: {periodo}   |   Versão: {versao}   |   Status: {status}", sub_style))
    story.append(Paragraph(f"Gerado em: {_fmt_date(str(gerado_em)[:10])} — {gerado_por_nome or 'sistema'}", sub_style))
    story.append(Spacer(1, 0.4 * cm))

    # Registros table
    if registros:
        headers = ["Data", "Frente de Serviço", "Resultado", "Clima Manhã", "Clima Tarde", "Observação"]
        rows = [headers]
        for r in registros:
            rows.append([
                _fmt_date(str(r.get("data", ""))),
                str(r.get("frente_servico_nome") or r.get("frente_servico_id") or "—"),
                str(r.get("resultado") or "—"),
                str(r.get("tempo_manha") or "—"),
                str(r.get("tempo_tarde") or "—"),
                str(r.get("observacao") or "—")[:60],
            ])

        col_widths = [2.2 * cm, 5.5 * cm, 2.2 * cm, 2.5 * cm, 2.5 * cm, None]
        table = Table(rows, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, 0), 8),
            ("FONTSIZE",   (0, 1), (-1, -1), 7),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
            ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)
    else:
        story.append(Paragraph("Nenhum registro aprovado no período.", label_style))

    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(
        f"Tenant: {tenant_nome}   |   Total de registros: {len(registros)}",
        sub_style,
    ))

    doc.build(story)
    return buffer.getvalue()


def _fmt_date(value: str) -> str:
    if not value or len(value) < 10:
        return value or ""
    try:
        d = date.fromisoformat(value[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return value[:10]
