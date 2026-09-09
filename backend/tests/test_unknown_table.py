"""Regression coverage for unknown tables following the document header."""

import io
import unittest

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.main import app


def unknown_table_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 9)
    metadata = [
        "PRODUTO: REINI TESTE",
        "LOTE: X-1    DATA: 01/01/2026    NF: 9",
        "CLIENTE: LATICINIOS KIFORMAGGIO LTDA",
    ]
    for row, text in enumerate(metadata):
        pdf.drawString(35, 760 - row * 17, text)

    top = 690
    xs = [35, 145, 250, 365, 490, 570]
    ys = [top, top - 24, top - 48, top - 72]
    for x in xs:
        pdf.line(x, ys[-1], x, ys[0])
    for y in ys:
        pdf.line(xs[0], y, xs[-1], y)
    cells = [
        ["ITEM", "FORMULA", "METODO", "ESPECIF.", "OBSERVACOES"],
        ["ASPECTO", "LIQUIDO", "VISUAL", "CONFORME", "OK"],
        ["COR", "AMARELADO", "VISUAL", "CONFORME", "OK"],
    ]
    for row, values in enumerate(cells):
        for col, value in enumerate(values):
            pdf.drawString(xs[col] + 3, top - 16 - row * 24, value)
    pdf.drawString(35, 575, "Este certificado esta baseado nas informações do fabricante.")
    pdf.drawString(35, 558, "QUIMICO RESPONSAVEL")
    pdf.save()
    return out.getvalue()


def two_column_metadata_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    xs, ys = [35, 220, 560], [760, 730, 700, 670]
    for x in xs:
        pdf.line(x, ys[-1], x, ys[0])
    for y in ys:
        pdf.line(xs[0], y, xs[-1], y)
    cells = [
        ["PRODUTO:", "Produto em tabela"],
        ["LOTE:", "T-22"],
        ["CLIENTE:", "Cliente em tabela"],
    ]
    for row, values in enumerate(cells):
        pdf.drawString(xs[0] + 4, ys[row + 1] + 9, values[0])
        pdf.drawString(xs[1] + 4, ys[row + 1] + 9, values[1])
    pdf.drawString(35, 630, "ITEM UNIDADE ESPECIFICACAO RESULTADO OBSERVACAO")
    pdf.drawString(35, 610, "COR kg AZUL OK")
    pdf.save()
    return out.getvalue()


class UnknownTableRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_unknown_ruled_table_does_not_pollute_cliente(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("unknown.pdf", unknown_table_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["fields"]["cliente"], "LATICINIOS KIFORMAGGIO LTDA")
        self.assertEqual(body["tables"], [])
        self.assertTrue(body["warnings"])

    def test_two_column_metadata_is_not_treated_as_structured_table(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("metadata-table.pdf", two_column_metadata_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["fields"]["produto"], "Produto em tabela")
        self.assertEqual(body["fields"]["lote"], "T-22")
        self.assertEqual(body["fields"]["cliente"], "Cliente em tabela")
        self.assertEqual(body["tables"], [])


if __name__ == "__main__":
    unittest.main()
