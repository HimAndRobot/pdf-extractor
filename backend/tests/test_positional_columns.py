"""Regression fixtures for the report's physical five-column contract.

The labels in these reports are unreliable OCR/text extraction signals.  The
five cells are positional: ITEM, FORMULA UNID., METODO ESPECIF., ANALITICO,
OBSERVACOES.  These tests intentionally use fractured and multi-line labels.
"""

import io
import unittest

import pdfplumber
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.structured_parser import parse


FIVE_KEYS = ["item", "formula_unid", "metodo_especif", "analitico", "observacoes"]


def _grid(pdf, xs, top, row_height, rows, *, multiline_header=False):
    bottom = top - row_height * len(rows)
    for x in xs:
        pdf.line(x, bottom, x, top)
    for index in range(len(rows) + 1):
        pdf.line(xs[0], top - row_height * index, xs[-1], top - row_height * index)
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            if not value:
                continue
            if multiline_header and row == 0 and col in (1, 2):
                first, second = value
                pdf.drawString(xs[col] + 3, top - 15, first)
                pdf.drawString(xs[col] + 3, top - 27, second)
            else:
                pdf.drawString(xs[col] + 3, top - 16 - row * row_height, value)


def malformed_ruled_five_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(35, 760, "CLIENTE: Cliente Posicional")
    _grid(pdf, [35, 145, 255, 365, 475, 570], 700, 34, [
        ["ITEM", ("FORMU", "LA UNID."), ("METODO", "ESPECIF."), "ANALITICO", "OBSERVA"],
        ["COR", "FORMULA A", "VISUAL", "APROVADO", "OK"],
        ["ASPECTO", None, "FISICO", "CONFORME", ""],
    ], multiline_header=True)
    # Finish the final header glyph in the fifth physical cell separately.
    pdf.drawString(518, 685, "COES")
    pdf.drawString(35, 540, "QUIMICO RESPONSAVEL: Rodape")
    pdf.save()
    return out.getvalue()


def malformed_borderless_five_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(35, 760, "CLIENTE: Cliente Borderless")
    xs = [45, 155, 275, 385, 480]
    # Header cells are separated by large x gaps, but labels are split over
    # lines and glyph fragments so raw header matching cannot identify them.
    for x, value in zip(xs, ["ITEM", "FORMU", "METODO", "ANALITICO", "OBSERVA"]):
        pdf.drawString(x, 700, value)
    pdf.drawString(155, 688, "LA UNID.")
    pdf.drawString(275, 688, "ESPECIF.")
    pdf.drawString(522, 700, "COES")
    pdf.setFont("Helvetica", 8)
    for y, values in [(660, ["COR", "kg", "VISUAL", "11", "OK"]),
                      (640, ["ASPECTO", None, "FISICO", "APROVADO", None]),
                      (620, ["TEXTURA", "g", "SENSORIAL", "CONFORME", ""])]:
        for x, value in zip(xs, values):
            if value:
                pdf.drawString(x, y, value)
    pdf.drawString(35, 580, "Este certificado permanece válido.")
    pdf.save()
    return out.getvalue()


def three_then_two_header_borderless_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(45, 700, "HEADER-A")
    pdf.drawString(275, 700, "HEADER-C")
    pdf.drawString(480, 700, "HEADER-E")
    pdf.drawString(155, 688, "HEADER-B")
    pdf.drawString(385, 688, "HEADER-D")
    pdf.setFont("Helvetica", 8)
    for y, values in [(660, ["COR", "kg", "VISUAL", "11", "OK"]),
                      (640, ["ASPECTO", "g", "FISICO", "APROVADO", "OBS"]),
                      (620, ["TEXTURA", "mg", "SENSORIAL", "CONFORME", "NOTA"])] :
        for x, value in zip([45, 155, 275, 385, 480], values):
            pdf.drawString(x, y, value)
    pdf.save(); return out.getvalue()


def reordered_header_ruled_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 9)
    _grid(pdf, [35, 150, 265, 380, 475, 570], 700, 25, [
        ["OBSERVACOES", "ANALITICO", "ITEM", "METODO", "FORMULA"],
        ["OK", "CONFORME", "COR", "VISUAL", "kg"],
    ])
    pdf.save(); return out.getvalue()


def clipped_short_items_with_metadata_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(35, 770, "TRANSPORTADOR: PROPRIO LOTE INT.: LACRES:")
    pdf.drawString(35, 755, "QUANTIDADE: 50 LACRES:")
    xs = [100, 200, 300, 400, 500, 570]; top = 700; height = 24
    rows = [["ITEM", "FORMULA", "METODO", "ANALITICO", "OBSERVACOES"],
            ["COR", "kg", "VISUAL", "OK", ""],
            ["ASPECTO", "g", "FISICO", "APROVADO", ""],
            ["DENSIDADE", "g/ml", "LAB", "1,1", "OK"]]
    for x in xs: pdf.line(x, top - height * len(rows), x, top)
    for i in range(len(rows) + 1): pdf.line(xs[0], top - height * i, xs[-1], top - height * i)
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            if value: pdf.drawString((80 if c == 0 else xs[c]) + 2, top - 16 - r * height, value)
    pdf.save(); return out.getvalue()


def three_column_control_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 9)
    _grid(pdf, [35, 210, 390, 570], 700, 25, [
        ["ESPECIFICACAO", "PARAMETRO", "RESULTADO"],
        ["COR", "AZUL", "OK"],
    ])
    pdf.save()
    return out.getvalue()


class PositionalColumnTests(unittest.TestCase):
    def test_malformed_ruled_five_maps_by_physical_position(self):
        pages, _, _, tables, _ = parse(malformed_ruled_five_pdf())
        self.assertEqual(pages, 1)
        self.assertEqual(tables[0]["rows"], [
            {"item": "COR", "formula_unid": "FORMULA A", "metodo_especif": "VISUAL", "analitico": "APROVADO", "observacoes": "OK"},
            {"item": "ASPECTO", "formula_unid": None, "metodo_especif": "FISICO", "analitico": "CONFORME", "observacoes": None},
        ])
        self.assertEqual(tables[0]["columns"], FIVE_KEYS)

    def test_malformed_borderless_five_uses_five_bands_and_keeps_empty_cells(self):
        _, _, _, tables, _ = parse(malformed_borderless_five_pdf())
        self.assertEqual(tables[0]["columns"], FIVE_KEYS)
        self.assertEqual(len(tables[0]["rows"]), 3)
        self.assertIsNone(tables[0]["rows"][1]["formula_unid"])
        self.assertIsNone(tables[0]["rows"][1]["observacoes"])

    def test_three_column_contract_is_unchanged(self):
        _, _, _, tables, _ = parse(three_column_control_pdf())
        self.assertEqual(tables[0]["columns"], ["especificacao", "parametro", "resultado"])
        self.assertEqual(tables[0]["rows"][0], {"especificacao": "COR", "parametro": "AZUL", "resultado": "OK"})

    def test_three_then_two_header_lines_infer_five_physical_bands(self):
        _, _, _, tables, _ = parse(three_then_two_header_borderless_pdf())
        self.assertEqual(tables[0]["columns"], FIVE_KEYS)
        self.assertEqual(len(tables[0]["rows"]), 3)
        self.assertEqual(tables[0]["rows"][0], {"item": "COR", "formula_unid": "kg", "metodo_especif": "VISUAL", "analitico": "11", "observacoes": "OK"})
        self.assertEqual(tables[0]["rows"][1]["observacoes"], "OBS")

    def test_five_alphabetic_values_are_data_and_header_order_is_ignored(self):
        _, _, _, tables, _ = parse(reordered_header_ruled_pdf())
        self.assertEqual(tables[0]["rows"][0], {"item": "OK", "formula_unid": "CONFORME", "metodo_especif": "COR", "analitico": "VISUAL", "observacoes": "kg"})

    def test_clipped_short_items_and_metadata_boundaries(self):
        pages, _, fields, tables, _ = parse(clipped_short_items_with_metadata_pdf())
        self.assertEqual(pages, 1)
        self.assertEqual(fields["transportadora"], "PROPRIO")
        self.assertEqual(fields["quantidade"], "50")
        self.assertEqual([row["item"] for row in tables[0]["rows"]], ["COR", "ASPECTO", "DENSIDADE"])
        self.assertEqual(tables[0]["rows"][2]["analitico"], "1,1")


if __name__ == "__main__":
    unittest.main()
