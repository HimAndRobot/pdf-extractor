"""Endpoint integration tests for generic borderless tables."""

import io
import unittest

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.main import app


def borderless_unknown_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter); pdf.setFont("Helvetica", 9)
    # Aligned metadata fields precede the table and must not absorb its text.
    pdf.drawString(35, 760, "PRODUTO: Solucao Aurora")
    pdf.drawString(230, 760, "LOTE: B-17")
    pdf.drawString(400, 760, "QUANTIDADE: 12 UND")
    pdf.drawString(35, 742, "CLIENTE: Oficina Aurora")
    xs = [35, 220, 390, 570]
    rows = [
        ["nome do item", "unidade medida", "resultado final"],
        ["Concentrado Alfa", "litros", "aprovado"],
        ["Material Beta", "kg", "reprovado"],
    ]
    y = 680
    for row in rows:
        for index, value in enumerate(row):
            pdf.drawString(xs[index], y, value)
        y -= 22
    pdf.drawString(35, 590, "Este certificado esta baseado nas informações do fabricante.")
    pdf.save(); return out.getvalue()


def borderless_without_header_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter); pdf.setFont("Helvetica", 9)
    xs = [35, 220, 390, 570]
    rows = [["Primeiro valor", "Texto livre", "11"], ["Segundo valor", "Outro texto", "22"]]
    y = 700
    for row in rows:
        for index, value in enumerate(row):
            pdf.drawString(xs[index], y, value)
        y -= 22
    pdf.save(); return out.getvalue()


class GenericApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_unknown_borderless_table_preserves_dynamic_headers_and_metadata(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("generic-borderless.pdf", borderless_unknown_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["produto"], "Solucao Aurora")
        self.assertEqual(body["lote"], "B-17")
        self.assertEqual(body["quantidade"], "12 UND")
        self.assertEqual(body["cliente"], "Oficina Aurora")
        self.assertEqual(len(body["tabelas"]), 1)
        table = body["tabelas"][0]
        self.assertEqual(table["linhas"], [
            {"nome_do_item": "Concentrado Alfa", "unidade_medida": "litros", "resultado_final": "aprovado"},
            {"nome_do_item": "Material Beta", "unidade_medida": "kg", "resultado_final": "reprovado"},
        ])
        self.assertNotIn("Este certificado", body["cliente"] or "")

    def test_borderless_data_without_header_keeps_first_text_and_numeric_rows(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("generic-no-header.pdf", borderless_without_header_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["tabelas"]), 1)
        table = body["tabelas"][0]
        self.assertEqual(len(table["linhas"]), 2)


if __name__ == "__main__":
    unittest.main()
