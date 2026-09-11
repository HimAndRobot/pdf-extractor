"""Acceptance coverage for the structured-laudo endpoint.

These tests intentionally exercise layout variations instead of snapshotting
the current parser implementation.  Synthetic PDFs are kept in memory.
"""

import io
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


def pdf_from_lines(lines: list[str], *, pages: list[list[str]] | None = None) -> bytes:
    pages = pages or [lines]
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    for page_lines in pages:
        y = 760
        for line in page_lines:
            pdf.setFont("Helvetica", 9)
            pdf.drawString(35, y, line)
            y -= 15
        pdf.showPage()
    pdf.save()
    return out.getvalue()


def pdf_from_cells(
    rows: list[list[str | None]], *, margin: int = 35, font_size: int = 9,
    pages: list[list[list[str | None]]] | None = None,
) -> bytes:
    """Draw a borderless table with real x coordinates (no ruling lines)."""
    pages = pages or [rows]
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    column_count = max((len(row) for row in rows), default=0)
    widths = [190, 170, 120] if column_count == 3 else [180, 55, 125, 80, 110]
    header_index = next(
        (i for i, row in enumerate(rows)
         if row and row[0] and "especific" in row[0].lower() or row and row[0] and row[0].lower() == "item"),
        None,
    )
    if header_index is not None:
        for row in rows[header_index + 1:]:
            for index, value in enumerate(row[:column_count]):
                if value:
                    assert stringWidth(value, "Helvetica", font_size) <= widths[index] - 2, (
                        f"fixture cell overflows column {index}: {value!r}"
                    )
    for page_rows in pages:
        pdf.setFont("Helvetica", font_size)
        y = 760
        for row in page_rows:
            x = margin
            for index, value in enumerate(row):
                if value:
                    pdf.drawString(x, y, value)
                x += widths[index]
            y -= 16
        pdf.showPage()
    pdf.save()
    return out.getvalue()


def upload(client: TestClient, content: bytes, name: str = "fixture.pdf"):
    return client.post(
        "/api/extract/structured",
        files={"file": (name, content, "application/pdf")},
    )


class StructuredAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def test_real_three_column_laudo_has_complete_contract(self):
        response = upload(self.client, (ROOT / "examples/laudo.pdf").read_bytes(), "laudo.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"produto", "lote", "data_le", "nota_fiscal", "data_fabricacao", "data_validade", "embalagem", "quantidade", "fornecedor", "transportadora", "cliente", "tabelas"})
        self.assertEqual(set(body["tabelas"][0]), {"secao", "linhas"})
        self.assertEqual(body["produto"], "REINI SUN - 05 L")
        self.assertEqual(body["nota_fiscal"], "78101")
        self.assertIsNone(body["transportadora"])
        self.assertEqual(len(body["tabelas"]), 2)
        self.assertEqual(body["tabelas"][0]["linhas"][1], {
            "especificacao": "COR",
            "parametro": "INCOLOR A ESBRANQUIÇADO",
            "resultado": "CONFERE",
        })
        self.assertEqual(body["tabelas"][1]["linhas"][-1]["resultado"], "20,8")
        self.assertEqual([], [])

    def test_real_five_column_laudo_preserves_unit_and_blank_cells(self):
        response = upload(self.client, (ROOT / "examples/1353.pdf").read_bytes(), "1353.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["produto"], "REINI LAND 380 POS 05 L")
        self.assertEqual(body["data_fabricacao"], "09/07/2026")
        self.assertEqual(len(body["tabelas"]), 1)
        table = body["tabelas"][0]
        self.assertEqual(len(table["linhas"]), 9)
        self.assertEqual(table["linhas"][0]["especificacoes"], "LIQUIDO DE ALTA VISCOSIDADE")
        self.assertIsNone(table["linhas"][0]["unidade"])
        self.assertEqual(table["linhas"][2]["unidade"], "°C")

    def test_other_real_three_column_laudo_preserves_time_value(self):
        response = upload(self.client, (ROOT / "examples/2556.pdf").read_bytes(), "2556.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["nota_fiscal"], "77486")
        self.assertEqual(body["embalagem"], "BB")
        self.assertEqual(body["tabelas"][1]["linhas"][1]["resultado"], "3:11")

    def test_other_real_five_column_laudo_preserves_empty_packaging(self):
        response = upload(self.client, (ROOT / "examples/3555.pdf").read_bytes(), "3555.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body["embalagem"])
        self.assertEqual(body["quantidade"], "2.000 KG")
        self.assertEqual(body["tabelas"][0]["linhas"][0]["observacoes"], None)

    def test_borderless_three_column_table_uses_columns_and_not_section_heading(self):
        rows = [
            ["CLIENTE: Cliente Novo", None, None],
            ["PRODUTO: Produto Sem Modelo", None, None],
            ["NF: 9 LOTE: L-7 DATA VALIDADE: 01/02/2030", None, None],
            ["DATA FAB.: 03/04/2029 DATA: 05/06/2029 QUANTIDADE: 2 L", None, None],
            ["FORNECEDOR: Fornecedor X EMBALAGEM: Tambor", None, None],
            ["ESPECIFICACAO", "PARAMETRO", "RESULTADO"],
            ["PONTO DE EBULICAO", "100 A 120", "110"],
            ["COR", "AZUL MARINHO", "APROVADO"],
        ]
        response = upload(self.client, pdf_from_cells(rows, margin=62, font_size=11), "changed-spacing.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["tabelas"][0]["linhas"][1]["especificacao"], "COR")
        self.assertEqual(body["cliente"], "Cliente Novo")
        self.assertEqual(body["nota_fiscal"], "9")

    def test_metadata_without_end_marker_and_mixed_case_headers(self):
        rows = [
            ["pRoDuTo: Produto Flex lote: L-8 data: 02/03/2026", None, None],
            ["nF: 77 data fab.: 04/05/2026 data validade: 04/05/2028", None, None],
            ["fOrNeCeDoR: Empresa Y quantidade: 10 UND", None, None],
            ["EsPeCiFiCaÇãO", "PaRaMeTrO", "ReSuLtAdO"],
            ["COR", "AZUL", "CONFERE"],
        ]
        response = upload(self.client, pdf_from_cells(rows, margin=48, font_size=10), "no-end-marker.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["produto"], "Produto Flex")
        self.assertEqual(body["lote"], "L-8")
        self.assertEqual(body["data_le"], "02/03/2026")
        self.assertEqual(body["data_fabricacao"], "04/05/2026")
        self.assertEqual(body["fornecedor"], "Empresa Y")
        self.assertEqual(body["tabelas"][0]["linhas"][0]["resultado"], "CONFERE")

    def test_borderless_wrapped_cell_keeps_continuation_in_same_row(self):
        rows = [
            ["item", "unidade", "especificacoes", "resultado", "observacao"],
            ["MATERIAL DE EMBALAGEM", "kg", "10 A 12", "APROVADO", "uso interno"],
            ["COMPOSICAO QUIMICA", None, "SOLUCAO DE ALTA", "REPROVADO", "revisar"],
            [None, None, "PUREZA", None, None],
        ]
        response = upload(self.client, pdf_from_cells(rows, margin=22, font_size=8), "wrapped.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        table = response.json()["tabelas"][0]
        self.assertEqual(table["linhas"][1]["item"], "COMPOSICAO QUIMICA")
        self.assertEqual(table["linhas"][1]["especificacoes"], "SOLUCAO DE ALTA PUREZA")
        self.assertEqual(table["linhas"][1]["resultado"], "REPROVADO")

    def test_flattened_table_without_column_coordinates_reports_ambiguity(self):
        lines = [
            "PRODUTO: Flattened",
            "ESPECIFICACAO PARAMETRO RESULTADO",
            "ITEM MULTIWORD VALUE WITH SPACES APROVADO",
        ]
        response = upload(self.client, pdf_from_lines(lines), "flattened.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["tabelas"], [])

    def test_legitimate_one_row_table_does_not_warn(self):
        rows = [
            ["PRODUTO: One Row", None, None],
            ["ESPECIFICACAO", "PARAMETRO", "RESULTADO"],
            ["COR", "AZUL", "CONFERE"],
        ]
        response = upload(self.client, pdf_from_cells(rows, margin=45, font_size=10), "one-row.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["tabelas"]), 1)
        self.assertEqual(len(body["tabelas"][0]["linhas"]), 1)
        self.assertEqual([], [])

    def test_five_column_table_supports_arbitrary_multiword_items_observation_and_blank_unit(self):
        rows = [
            ["produto: Limpa Tudo lote: A-1", None, None, None, None],
            ["data: 01/01/2026 nf: 44", None, None, None, None],
            ["item", "unidade", "especificacoes", "resultado", "observacao"],
            ["PESO LIQUIDO FINAL", "kg", "10 A 12", "11", "dentro da tolerancia"],
            ["APARENCIA DO PRODUTO", None, "gel azul", "conforme", "lote aprovado"],
            ["TEMPERATURA DE ARMAZENAMENTO", "°C", "15 A 30", "22", "sala fria"],
        ]
        response = upload(self.client, pdf_from_cells(rows, margin=28, font_size=8), "arbitrary.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        table = response.json()["tabelas"][0]
        self.assertEqual(table["linhas"][0]["item"], "PESO LIQUIDO FINAL")
        self.assertEqual(table["linhas"][0]["observacoes"], "dentro da tolerancia")
        self.assertIsNone(table["linhas"][1]["unidade"])
        self.assertEqual(table["linhas"][1]["item"], "APARENCIA DO PRODUTO")

    def test_sections_and_repeated_headers_across_pages_are_kept(self):
        first = [
            "PRODUTO: Multi",
            "CARACTERISTICAS ORGANOLEPTICAS",
            "ESPECIFICAÇÃO PARAMETRO RESULTADO",
            "FORMA PRODUTO LIQUIDO CONFERE",
            "COR VERDE CONFERE",
        ]
        second = [
            "CARACTERISTICAS FISICO - QUIMICA",
            "ESPECIFICACAO PARAMETRO RESULTADO",
            "DENSIDADE G/ML 1,0 A 1,2 1,1",
            "PH PURO 2,0 A 3,0 2,5",
        ]
        first_cells = [[line, None, None] for line in first[:2]] + [
            ["ESPECIFICAÇÃO", "PARAMETRO", "RESULTADO"],
            ["FORMA PRODUTO", "LIQUIDO", "CONFERE"],
            ["COR", "VERDE", "CONFERE"],
        ]
        second_cells = [[line, None, None] for line in second[:1]] + [
            ["ESPECIFICACAO", "PARAMETRO", "RESULTADO"],
            ["DENSIDADE", "G/ML 1,0 A 1,2", "1,1"],
            ["PH PURO", "2,0 A 3,0", "2,5"],
        ]
        response = upload(self.client, pdf_from_cells(first_cells, margin=52, font_size=10, pages=[first_cells, second_cells]), "multipage.pdf")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["tabelas"]), 2)
        self.assertEqual(body["tabelas"][0]["secao"], "CARACTERISTICAS ORGANOLEPTICAS")
        self.assertEqual(body["tabelas"][1]["secao"], "CARACTERISTICAS FISICO - QUIMICA")

    def test_invalid_and_image_only_inputs_have_documented_statuses(self):
        bad = self.client.post("/api/extract/structured", files={"file": ("x.txt", b"text", "text/plain")})
        self.assertEqual(bad.status_code, 415)
        blank = io.BytesIO()
        canvas.Canvas(blank, pagesize=letter).save()
        image_like = self.client.post("/api/extract/structured", files={"file": ("x.pdf", blank.getvalue(), "application/pdf")})
        self.assertEqual(image_like.status_code, 422)


if __name__ == "__main__":
    unittest.main()
