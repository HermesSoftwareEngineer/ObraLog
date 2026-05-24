"""Excel export for diários de obra using openpyxl."""
from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path
from typing import Any

UPLOAD_DIR = Path(os.environ.get("REGISTRO_IMAGENS_DIR", str(Path("backend") / "uploads" / "registros")))


def gerar_excel_diario(diario: dict, registros: list[dict]) -> bytes:
    """Generate an Excel workbook for a diário de obra. Returns raw xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.utils import get_column_letter

    wb = Workbook()

    # ---- Sheet 1: Registros ------------------------------------------------
    ws = wb.active
    ws.title = "Registros"

    green = "2D6A4F"
    light_green = "B7E4C7"
    grey_row = "F5F5F5"
    header_font = Font(bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill("solid", fgColor=green)
    label_font = Font(bold=True, size=10)
    label_fill = PatternFill("solid", fgColor=light_green)
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    obra_nome = diario.get("obra_nome") or f"Obra {diario.get('obra_id', '')}"
    tipo = diario.get("tipo", "diario").capitalize()
    data_inicio = _fmt_date(str(diario.get("data_inicio", "")))
    data_fim = _fmt_date(str(diario.get("data_fim", "")))
    periodo = f"{data_inicio}" if data_inicio == data_fim else f"{data_inicio} a {data_fim}"
    versao = diario.get("versao_atual", 1)
    status = diario.get("status", "rascunho").capitalize()
    gerado_por = diario.get("gerado_por_nome", "sistema")
    tenant_nome = diario.get("tenant_nome", "")

    # Header block
    header_data = [
        ("Diário de Obra", f"{tipo} — {obra_nome}"),
        ("Período", periodo),
        ("Versão", str(versao)),
        ("Status", status),
        ("Empresa", tenant_nome),
        ("Gerado por", gerado_por),
    ]
    for row_idx, (label, value) in enumerate(header_data, start=1):
        ws.cell(row=row_idx, column=1, value=label).font = label_font
        ws.cell(row=row_idx, column=1).fill = label_fill
        ws.cell(row=row_idx, column=2, value=value)
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 50

    blank_row = len(header_data) + 2

    # Table headers
    col_headers = ["#", "Data", "Frente de Serviço", "Resultado", "Clima Manhã", "Clima Tarde", "Observação", "Status", "Imagens"]
    for col_idx, h in enumerate(col_headers, start=1):
        cell = ws.cell(row=blank_row, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        cell.border = border

    col_widths = [5, 14, 30, 12, 14, 14, 45, 12, 10]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Data rows
    has_images = False
    for row_offset, r in enumerate(registros):
        row_num = blank_row + 1 + row_offset
        fill = PatternFill("solid", fgColor=grey_row) if row_offset % 2 == 1 else PatternFill()
        imagem_count = len(r.get("imagens") or [])
        if imagem_count:
            has_images = True

        values = [
            row_offset + 1,
            _fmt_date(str(r.get("data", ""))),
            str(r.get("frente_servico_nome") or r.get("frente_servico_id") or "—"),
            r.get("resultado"),
            str(r.get("tempo_manha") or "—"),
            str(r.get("tempo_tarde") or "—"),
            str(r.get("observacao") or ""),
            str(r.get("status") or "—"),
            imagem_count,
        ]
        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=val)
            cell.border = border
            if fill.fgColor.value != "00000000":
                cell.fill = fill

    # ---- Sheet 2: Imagens (one section per registro) -----------------------
    if has_images:
        ws2 = wb.create_sheet("Imagens")
        ws2.column_dimensions["A"].width = 20
        ws2.column_dimensions["B"].width = 30
        ws2.column_dimensions["C"].width = 20
        ws2.column_dimensions["D"].width = 80

        img_row = 1
        ws2.cell(row=img_row, column=1, value="Registro #").font = Font(bold=True)
        ws2.cell(row=img_row, column=2, value="Data").font = Font(bold=True)
        ws2.cell(row=img_row, column=3, value="Imagem #").font = Font(bold=True)
        ws2.cell(row=img_row, column=4, value="Caminho / URL").font = Font(bold=True)
        img_row += 1

        for seq, r in enumerate(registros, start=1):
            imagens = r.get("imagens") or []
            for img_seq, img in enumerate(imagens, start=1):
                ws2.cell(row=img_row, column=1, value=seq)
                ws2.cell(row=img_row, column=2, value=_fmt_date(str(r.get("data", ""))))
                ws2.cell(row=img_row, column=3, value=img_seq)

                path = img.get("storage_path") or ""
                url = img.get("external_url") or ""
                display = url or path
                ws2.cell(row=img_row, column=4, value=display)

                # Try to embed image if local file exists
                if path:
                    local_path = Path(path)
                    if not local_path.is_absolute():
                        local_path = UPLOAD_DIR / local_path.name
                    if local_path.exists():
                        try:
                            xl_img = XLImage(str(local_path))
                            xl_img.height = 100
                            xl_img.width = 133
                            ws2.row_dimensions[img_row].height = 80
                            ws2.add_image(xl_img, f"E{img_row}")
                        except Exception:
                            pass

                img_row += 1

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _fmt_date(value: str) -> str:
    if not value or len(value) < 10:
        return value or ""
    try:
        d = date.fromisoformat(value[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return value[:10]
