"""Regression coverage for ruled grids whose text uses a displaced x system."""

import io
import unittest

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.structured_parser import parse


KEYS = ["item", "unidade", "especificacoes", "resultado", "observacoes"]
HEADERS = ["ITEM", "UNIDADE", "ESPECIFICACAO", "RESULTADO", "OBSERVACAO"]


def displaced_grid_pdf(offset: float = 0, scale: float = 1.0, font_size: int = 9) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(800, 800))
    grid = [80, 210, 265, 355, 410, 560]
    text = [20, 150, 210, 300, 355]
    grid = [value * scale + offset for value in grid]
    text = [value * scale + offset for value in text]
    for x in grid:
        pdf.line(x, 600, x, 720)
    for y in [720, 690, 660, 630, 600]:
        pdf.line(grid[0], y, grid[-1], y)
    pdf.setFont("Helvetica", font_size)
    new_headers = ["ITEM", "FORMULA UNID.", "METODO ESPECIF.", "ANALITICO", "OBSERVACOES"]
    for x, value in zip(text, new_headers):
        pdf.drawString(x, 704, value)
    for row_index, values in enumerate([
        ["AMOSTRA-X", None, "VISUAL", "11", None],
        ["MATERIAL-Y", None, "FISICO", "CONFORME", None],
    ]):
        for x, value in zip(text, values):
            if value is not None:
                pdf.drawString(x, 674 - row_index * 30, value)
    pdf.save()
    return out.getvalue()


def normal_grid_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    xs = [35, 145, 255, 365, 475, 585]
    for x in xs:
        pdf.line(x, 600, x, 720)
    for y in [720, 690, 660, 630, 600]:
        pdf.line(xs[0], y, xs[-1], y)
    pdf.setFont("Helvetica", 9)
    for x, value in zip(xs, ["ITEM", "FORMULA UNID.", "METODO ESPECIF.", "ANALITICO", "OBSERVACOES"]):
        pdf.drawString(x + 3, 704, value)
    for row_y, values in [(674, ["COR", "kg", "VISUAL", None, None]), (644, ["ASPECTO", "g", "FISICO", None, None])]:
        for x, value in zip(xs, values):
            if value is not None:
                pdf.drawString(x + 3, row_y, value)
    pdf.save()
    return out.getvalue()


class DisplacedGridTests(unittest.TestCase):
    def test_translated_and_scaled_text_coordinates_keep_physical_values(self):
        for index, (offset, scale, font_size) in enumerate([(0, 0.8, 8), (20, 1.0, 9), (20, 1.2, 11)], start=1):
            with self.subTest(case=index):
                tables = parse(displaced_grid_pdf(offset, scale, font_size))[3]
                self.assertTrue(tables)
                self.assertEqual(tables[0]["columns"], KEYS)
                self.assertEqual(tables[0]["rows"], [
                    {"item": "AMOSTRA-X", "unidade": None, "especificacoes": "VISUAL", "resultado": "11", "observacoes": None},
                    {"item": "MATERIAL-Y", "unidade": None, "especificacoes": "FISICO", "resultado": "CONFORME", "observacoes": None},
                ])

    def test_normal_grid_does_not_shift_blank_trailing_cells(self):
        tables = parse(normal_grid_pdf())[3]
        self.assertTrue(tables)
        self.assertEqual(tables[0]["rows"], [
            {"item": "COR", "unidade": "kg", "especificacoes": "VISUAL", "resultado": None, "observacoes": None},
            {"item": "ASPECTO", "unidade": "g", "especificacoes": "FISICO", "resultado": None, "observacoes": None},
        ])


if __name__ == "__main__":
    unittest.main()
