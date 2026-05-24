"""Word export for diários de obra using python-docx."""
from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path

UPLOAD_DIR = Path(os.environ.get("REGISTRO_IMAGENS_DIR", str(Path("backend") / "uploads" / "registros")))


def gerar_word_diario(diario: dict, registros: list[dict]) -> bytes:
    """Generate a Word document for a diário de obra. Returns raw docx bytes."""
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1.2)
        section.right_margin = Inches(1.2)

    obra_nome = diario.get("obra_nome") or f"Obra {diario.get('obra_id', '')}"
    tipo = diario.get("tipo", "diario").capitalize()
    data_inicio = _fmt_date(str(diario.get("data_inicio", "")))
    data_fim = _fmt_date(str(diario.get("data_fim", "")))
    periodo = f"{data_inicio}" if data_inicio == data_fim else f"{data_inicio} a {data_fim}"
    versao = diario.get("versao_atual", 1)
    status = diario.get("status", "rascunho").capitalize()
    gerado_por = diario.get("gerado_por_nome", "sistema")
    tenant_nome = diario.get("tenant_nome", "")

    # Title
    title = doc.add_heading(f"Diário de Obra — {tipo}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_heading_color(title, (45, 106, 79))

    sub = doc.add_paragraph(obra_nome)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].bold = True
    sub.runs[0].font.size = Pt(14)

    doc.add_paragraph()

    # Info table
    info_tbl = doc.add_table(rows=5, cols=2)
    info_tbl.style = "Table Grid"
    info_data = [
        ("Período", periodo),
        ("Versão", str(versao)),
        ("Status", status),
        ("Empresa", tenant_nome),
        ("Gerado por", gerado_por),
    ]
    for i, (label, value) in enumerate(info_data):
        info_tbl.cell(i, 0).text = label
        info_tbl.cell(i, 0).paragraphs[0].runs[0].bold = True
        _set_cell_bg(info_tbl.cell(i, 0), "B7E4C7")
        info_tbl.cell(i, 1).text = value

    doc.add_paragraph()

    # Registros heading
    heading = doc.add_heading("Registros", level=1)
    _set_heading_color(heading, (45, 106, 79))

    if not registros:
        doc.add_paragraph("Nenhum registro no período.")
    else:
        col_names = ["#", "Data", "Frente de Serviço", "Resultado", "Manhã", "Tarde", "Observação", "Status"]
        tbl = doc.add_table(rows=1, cols=len(col_names))
        tbl.style = "Table Grid"
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Header row
        hdr_cells = tbl.rows[0].cells
        for i, name in enumerate(col_names):
            hdr_cells[i].text = name
            run = hdr_cells[i].paragraphs[0].runs[0]
            run.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            _set_cell_bg(hdr_cells[i], "2D6A4F")

        # Data rows
        for seq, r in enumerate(registros, start=1):
            row_cells = tbl.add_row().cells
            values = [
                str(seq),
                _fmt_date(str(r.get("data", ""))),
                str(r.get("frente_servico_nome") or r.get("frente_servico_id") or "—"),
                str(r.get("resultado") if r.get("resultado") is not None else "—"),
                str(r.get("tempo_manha") or "—"),
                str(r.get("tempo_tarde") or "—"),
                str(r.get("observacao") or ""),
                str(r.get("status") or "—"),
            ]
            bg = "F5F5F5" if seq % 2 == 0 else "FFFFFF"
            for i, val in enumerate(values):
                row_cells[i].text = val
                _set_cell_bg(row_cells[i], bg)

    # Images section
    registros_com_imagem = [r for r in registros if r.get("imagens")]
    if registros_com_imagem:
        doc.add_page_break()
        heading2 = doc.add_heading("Imagens por Registro", level=1)
        _set_heading_color(heading2, (45, 106, 79))

        for seq, r in enumerate(registros_com_imagem, start=1):
            imagens = r.get("imagens") or []
            reg_title = doc.add_heading(
                f"Registro #{seq} — {_fmt_date(str(r.get('data', '')))} — {r.get('frente_servico_nome') or ''}",
                level=2,
            )

            for img in imagens:
                path = img.get("storage_path") or ""
                url = img.get("external_url") or ""

                if path:
                    local_path = Path(path)
                    if not local_path.is_absolute():
                        local_path = UPLOAD_DIR / local_path.name
                    if local_path.exists():
                        try:
                            doc.add_picture(str(local_path), width=Inches(3))
                            continue
                        except Exception:
                            pass

                # fallback: show URL as text
                ref = url or path
                if ref:
                    p = doc.add_paragraph(f"[Imagem: {ref}]")
                    p.runs[0].italic = True

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _fmt_date(value: str) -> str:
    if not value or len(value) < 10:
        return value or ""
    try:
        d = date.fromisoformat(value[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return value[:10]


def _set_heading_color(paragraph, rgb: tuple[int, int, int]) -> None:
    for run in paragraph.runs:
        run.font.color.rgb = RGBColor(*rgb)


def _set_cell_bg(cell, hex_color: str) -> None:
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)
