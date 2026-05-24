"""PDF generation for diários de obra using reportlab."""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any


# Canonical column order for campos_ativos keys (skip "frente_servico" — redundant per-table)
_CAMPOS_ORDER = [
    ("estaca_inicial", "Est. Inicial"),
    ("estaca_final", "Est. Final"),
    ("estaca", "Localização"),
    ("resultado", "Resultado"),
    ("lado_pista", "Lado"),
    ("tempo_manha", "Manhã"),
    ("tempo_tarde", "Tarde"),
]


def _fetch_image_bytes(img: dict, timeout: int = 6) -> bytes | None:
    url = img.get("external_url") or ""
    if url and url.startswith(("http://", "https://")):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "ObraLog/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception:
            pass
    storage_path = img.get("storage_path") or ""
    if storage_path:
        try:
            from pathlib import Path
            p = Path(storage_path)
            if p.exists():
                return p.read_bytes()
        except Exception:
            pass
    return None


def _campo_value(r: dict, chave: str) -> str:
    if chave in ("estaca_inicial", "estaca_final", "resultado"):
        v = r.get(chave)
        return f"{v:.2f}" if isinstance(v, (int, float)) else ("—" if v is None else str(v))
    if chave == "estaca":
        return str(r.get("estaca") or "—")
    if chave == "lado_pista":
        return str(r.get("lado_pista") or "—")
    if chave in ("tempo_manha", "tempo_tarde"):
        return str(r.get(chave) or "—")
    # extras from metadata_json
    return str((r.get("metadata_json") or {}).get(chave) or "—")


def _build_columns(schema: dict) -> list[tuple[str, str]]:
    """Returns [(chave, label)] for the given schema, in canonical order."""
    campos_ativos = schema.get("campos_ativos") or {}
    campos_extras = schema.get("campos_extras") or []
    cols = []
    for chave, label in _CAMPOS_ORDER:
        if campos_ativos.get(chave):
            cols.append((chave, label))
    for extra in campos_extras:
        chave = extra.get("key") or extra.get("chave") or ""
        label = extra.get("label") or chave
        if chave:
            cols.append((chave, label))
    # Fallback: if schema is empty, show resultado + clima
    if not cols:
        cols = [("resultado", "Resultado"), ("tempo_manha", "Manhã"), ("tempo_tarde", "Tarde")]
    return cols


def gerar_pdf_diario(diario: dict, registros: list[dict], frentes_schemas: dict | None = None) -> bytes:
    """Generate a PDF for a diário de obra. Returns raw PDF bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    PAGE_W = A4[0] - 4 * cm  # usable width (2cm margins each side)

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
    frente_style = ParagraphStyle("frente", parent=styles["Heading2"], fontSize=11, spaceAfter=4,
                                  spaceBefore=10, textColor=colors.HexColor("#2d6a4f"))
    no_reg_style = ParagraphStyle("noreg", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    frentes_schemas = frentes_schemas or {}

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

    if not registros:
        story.append(Paragraph("Nenhum registro aprovado no período.", no_reg_style))
    else:
        # Group by frente_servico_id preserving insertion order
        grupos: dict = {}
        for r in registros:
            fid = r.get("frente_servico_id")
            grupos.setdefault(fid, []).append(r)

        for fid, regs in grupos.items():
            schema = frentes_schemas.get(fid, {})
            frente_nome = schema.get("nome") or regs[0].get("frente_servico_nome") or "Sem frente"
            cols = _build_columns(schema)

            story.append(Paragraph(f"Frente: {frente_nome}", frente_style))

            # Build table: header + data rows (with merged photo sub-rows)
            header_labels = ["Data"] + [label for _, label in cols] + ["Observação", "Fotos"]
            n_data_cols = len(header_labels) - 1  # all except Fotos

            # Fixed widths: Date=2cm, Fotos=3.2cm, rest split evenly
            fotos_w = 3.2 * cm
            date_w = 2.2 * cm
            rem_w = PAGE_W - date_w - fotos_w
            mid_cols = len(header_labels) - 2  # between date and fotos
            mid_w = rem_w / mid_cols if mid_cols > 0 else rem_w
            col_widths = [date_w] + [mid_w] * mid_cols + [fotos_w]

            rows: list = [header_labels]
            span_cmds: list = []
            style_rows: list = []

            row_idx = 1  # 0 = header
            for r in regs:
                imagens = r.get("imagens") or []
                img_flowables: list = []
                for img in imagens:
                    img_bytes = _fetch_image_bytes(img)
                    if img_bytes:
                        try:
                            flowable = RLImage(io.BytesIO(img_bytes), width=2.8 * cm, height=2.8 * cm, kind="proportional")
                            img_flowables.append(flowable)
                        except Exception:
                            pass

                n_photo_rows = max(1, len(img_flowables))
                data_cells = (
                    [_fmt_date(str(r.get("data", "")))]
                    + [_campo_value(r, chave) for chave, _ in cols]
                    + [str(r.get("observacao") or "")]
                )

                for pi in range(n_photo_rows):
                    foto_cell = img_flowables[pi] if pi < len(img_flowables) else ("—" if pi == 0 else "")
                    if pi == 0:
                        rows.append(data_cells + [foto_cell])
                    else:
                        rows.append([""] * n_data_cols + [foto_cell])

                if n_photo_rows > 1:
                    for ci in range(n_data_cols):
                        span_cmds.append(("SPAN", (ci, row_idx), (ci, row_idx + n_photo_rows - 1)))

                bg = colors.white if (row_idx % 2 == 1) else colors.HexColor("#f0f0f0")
                for i in range(n_photo_rows):
                    style_rows.append(("BACKGROUND", (0, row_idx + i), (-1, row_idx + i), bg))

                row_idx += n_photo_rows

            base_style = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, 0), 8),
                ("FONTSIZE",   (0, 1), (-1, -1), 7),
                ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]

            tbl = Table(rows, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle(base_style + style_rows + span_cmds))
            story.append(tbl)
            story.append(Spacer(1, 0.3 * cm))

    story.append(Spacer(1, 0.4 * cm))
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
