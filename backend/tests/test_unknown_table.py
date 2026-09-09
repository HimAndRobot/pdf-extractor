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
        "CLIENTE: Fazenda Aurora",
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


def _ruled_table(pdf, xs, top, row_height, rows):
    assert all(len(row) == len(xs) - 1 for row in rows), "fixture row must match physical column count"
    bottom = top - row_height * len(rows)
    for x in xs:
        pdf.line(x, bottom, x, top)
    for index in range(len(rows) + 1):
        y = top - row_height * index
        pdf.line(xs[0], y, xs[-1], y)
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            if value:
                pdf.drawString(xs[col] + 3, top - 16 - row * row_height, value)


def unknown_three_column_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(35, 760, "CLIENTE: Cliente 3 desconhecido")
    _ruled_table(pdf, [35, 210, 390, 570], 700, 25, [
        ["AMOSTRA", "METODO", "NOTA"],
        ["ASPECTO", "VISUAL", "APROVADO"],
    ])
    pdf.save(); return out.getvalue()


def corrupted_header_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 9)
    _ruled_table(pdf, [35, 140, 245, 350, 455, 570], 750, 25, [
        ["ITEM", "FORMULÁ", "MÉTODO", "ESPECIF.", ""],
        ["COR", "AMARELO", "VISUAL", "OK", ""],
    ])
    pdf.save(); return out.getvalue()


def duplicate_header_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 9)
    _ruled_table(pdf, [35, 160, 285, 410, 570], 750, 25, [
        ["ITEM", "ITEM", "RESULTADO", "RESULTADO"],
        ["A", "B", "X", "Y"],
    ])
    pdf.save(); return out.getvalue()


def data_without_header_pdf() -> bytes:
    out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 9)
    _ruled_table(pdf, [35, 220, 390, 570], 750, 25, [
        ["VALOR A", "VALOR B", "VALOR C"],
        ["OUTRO A", "OUTRO B", "OUTRO C"],
    ])
    pdf.save(); return out.getvalue()


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
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_unknown_ruled_table_does_not_pollute_cliente(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("unknown.pdf", unknown_table_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["cliente"], "Fazenda Aurora")
        self.assertEqual(len(body["tabelas"][0]["linhas"]), 2)
        self.assertEqual(body["tabelas"][0]["linhas"][0], {
            "item": "ASPECTO", "formula": "LIQUIDO", "metodo": "VISUAL",
            "especif": "CONFORME", "observacoes": "OK",
        })

    def test_unknown_three_column_table_is_preserved_with_dynamic_columns(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("unknown-three.pdf", unknown_three_column_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        table = response.json()["tabelas"][0]
        self.assertEqual(table["linhas"][0]["nota"], "APROVADO")

    def test_repeated_unknown_header_is_not_returned_as_a_data_row(self):
        out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter); pdf.setFont("Helvetica", 9)
        _ruled_table(pdf, [35, 210, 390, 570], 750, 25, [
            ["AMOSTRA", "METODO", "NOTA"], ["A", "VISUAL", "OK"],
            ["AMOSTRA", "METODO", "NOTA"], ["B", "VISUAL", "OK"],
        ])
        pdf.save()
        response = self.client.post("/api/extract/structured", files={"file": ("repeat-unknown.pdf", out.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()["tabelas"][0]["linhas"]
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["amostra"] for row in rows], ["A", "B"])

    def test_corrupted_header_preserves_source_keys_and_blank_column(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("corrupted.pdf", corrupted_header_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        table = response.json()["tabelas"][0]
        self.assertIsNone(table["linhas"][0]["coluna_5"])

    def test_duplicate_source_headers_get_deterministic_suffixes(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("duplicates.pdf", duplicate_header_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_duplicate_headers_that_collide_with_suffix_are_all_unique(self):
        out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter); pdf.setFont("Helvetica", 9)
        _ruled_table(pdf, [35, 180, 325, 470], 750, 25, [
            ["ITEM", "ITEM_2", "ITEM"], ["A", "B", "C"],
        ])
        pdf.save()
        response = self.client.post("/api/extract/structured", files={"file": ("collision.pdf", out.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        table = response.json()["tabelas"][0]

    def test_sparse_unknown_rows_are_preserved_with_null_cells(self):
        out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter); pdf.setFont("Helvetica", 9)
        _ruled_table(pdf, [35, 180, 325, 470], 750, 25, [
            ["AMOSTRA", "METODO", "NOTA"], ["A", None, None], [None, "B", None],
        ])
        pdf.save()
        response = self.client.post("/api/extract/structured", files={"file": ("sparse.pdf", out.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()["tabelas"][0]["linhas"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"amostra": "A", "metodo": None, "nota": None})
        self.assertEqual(rows[1], {"amostra": None, "metodo": "B", "nota": None})

    def test_first_data_row_without_header_is_preserved_as_generic_columns(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("no-header.pdf", data_without_header_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        table = response.json()["tabelas"][0]
        self.assertEqual(table["linhas"][0]["coluna_1"], "VALOR A")

    def test_two_column_metadata_is_not_treated_as_structured_table(self):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": ("metadata-table.pdf", two_column_metadata_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["produto"], "Produto em tabela")
        self.assertEqual(body["lote"], "T-22")
        self.assertEqual(body["cliente"], "Cliente em tabela")
        self.assertEqual(body["tabelas"], [])

    def test_known_and_unknown_tables_on_same_page_are_both_returned(self):
        out = io.BytesIO(); pdf = canvas.Canvas(out, pagesize=letter); pdf.setFont("Helvetica", 8)
        _ruled_table(pdf, [35, 210, 390, 570], 750, 22, [
            ["ESPECIFICACAO", "PARAMETRO", "RESULTADO"], ["COR", "AZUL", "OK"],
        ])
        _ruled_table(pdf, [35, 160, 285, 410, 500, 570], 650, 22, [
            ["ITEM", "FORMULA", "METODO", "ESPECIF.", "OBSERVACOES"], ["X", "Y", "Z", "OK", "nota"],
        ])
        pdf.save()
        response = self.client.post("/api/extract/structured", files={"file": ("mixed.pdf", out.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["tabelas"]), 2)


if __name__ == "__main__":
    unittest.main()
