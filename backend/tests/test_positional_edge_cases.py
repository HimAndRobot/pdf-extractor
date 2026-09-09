"""Borderless five-column regressions for positional table extraction."""

import io
import unittest

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.main import app


FIVE_KEYS = ["item", "formula_unid", "metodo_especif", "analitico", "observacoes"]
OLD_HEADERS = ["ITEM", "UNIDADE", "ESPECIFICACAO", "RESULTADO", "OBSERVACAO"]
X = [40, 150, 260, 370, 480]


def _borderless_pdf(
    rows: list[list[str | None]], *, data_font: int, logo: bool = False, header: bool = True,
    data_start: int = 680,
) -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    if header:
        pdf.setFont("Helvetica-Bold", 11)
        for column, value in enumerate(OLD_HEADERS):
            pdf.drawString(X[column], 720, value)
    pdf.setFont("Helvetica", data_font)
    for row_index, row in enumerate(rows):
        y = (data_start if header else 720) - row_index * 24
        for column, value in enumerate(row):
            if value is not None:
                pdf.drawString(X[column], y, value)
    if logo:
        # A large, unrelated mark follows the header and must not cause the
        # sparse first data row to be classified as a repeated header.
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(575, 680, "LOGO")
    pdf.save()
    return out.getvalue()


def _extract(content: bytes, filename: str) -> list[dict[str, str | None]]:
    with TestClient(app) as client:
        response = client.post(
            "/api/extract/structured",
            files={"file": (filename, content, "application/pdf")},
        )
    if response.status_code != 200:
        raise AssertionError(f"{response.status_code}: {response.text}")
    tables = response.json()["tabelas"]
    assert len(tables) == 1
    assert tables[0]["linhas"]
    return tables[0]["linhas"]


def same_font_split_header_pdf() -> bytes:
    """Borderless report whose regular 8pt header matches its body font."""
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(35, 760, "CLIENTE: Cliente Mesmo Fonte")
    for x, value in zip([45, 155, 275, 385, 480], ["ITEM", "FORMU", "METODO", "ANALITICO", "OBSERVA"]):
        pdf.drawString(x, 700, value)
    pdf.drawString(155, 688, "LA UNID.")
    pdf.drawString(275, 688, "ESPECIF.")
    pdf.drawString(522, 700, "COES")
    for y, values in [(660, ["COR", "kg", "VISUAL", "11", "OK"]),
                      (640, ["ASPECTO", None, "FISICO", "APROVADO", None]),
                      (620, ["TEXTURA", "g", "SENSORIAL", "CONFORME", None])]:
        for x, value in zip([45, 155, 275, 385, 480], values):
            if value is not None:
                pdf.drawString(x, y, value)
    pdf.save()
    return out.getvalue()


class PositionalEdgeCaseTests(unittest.TestCase):
    def test_sparse_first_row_survives_large_mark_after_header(self):
        rows = _extract(
            _borderless_pdf([["COR", None, None, "OK", None], ["ASPECTO", "kg", "VISUAL", "APROVADO", "OBS"]], data_font=8, data_start=700),
            "sparse-borderless.pdf",
        )
        self.assertEqual(list(rows[0]), FIVE_KEYS)
        self.assertEqual(rows[0], {"item": "COR", "formula_unid": None, "metodo_especif": None, "analitico": "OK", "observacoes": None})

    def test_alphabetic_item_matching_header_is_data(self):
        rows = _extract(
            _borderless_pdf([["METODO", "kg", "VISUAL", "APROVADO", "OK"], ["COR", "g", "FISICO", "CONFORME", "OBS"]], data_font=11),
            "alphabetic-data.pdf",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["item"], "METODO")
        self.assertEqual(list(rows[0]), FIVE_KEYS)

    def test_five_alpha_rows_without_header_are_not_discarded(self):
        rows = _extract(
            _borderless_pdf(
                [["COR", "kg", "VISUAL", "CONFORME", "OK"], ["ASPECTO", "g", "FISICO", "APROVADO", "OBS"]],
                data_font=10,
                header=False,
            ),
            "alpha-without-header.pdf",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {"item": "COR", "formula_unid": "kg", "metodo_especif": "VISUAL", "analitico": "CONFORME", "observacoes": "OK"})
        self.assertEqual(list(rows[0]), FIVE_KEYS)

    def test_reordered_old_labels_do_not_change_physical_mapping(self):
        # Replace only the header text positions while retaining the same five
        # physical bands.  The data values must remain positionally assigned.
        out = io.BytesIO()
        pdf = canvas.Canvas(out, pagesize=letter)
        pdf.setFont("Helvetica-Bold", 11)
        for column, value in enumerate(["OBSERVACAO", "RESULTADO", "ESPECIFICACAO", "UNIDADE", "ITEM"]):
            pdf.drawString(X[column], 720, value)
        pdf.setFont("Helvetica", 10)
        for column, value in enumerate(["OBS", "OK", "COR", "kg", "AMOSTRA"]):
            pdf.drawString(X[column], 680, value)
        pdf.save()
        rows = _extract(out.getvalue(), "reordered-labels.pdf")
        self.assertEqual(rows[0], {"item": "OBS", "formula_unid": "OK", "metodo_especif": "COR", "analitico": "kg", "observacoes": "AMOSTRA"})
        self.assertEqual(list(rows[0]), FIVE_KEYS)

    def test_regular_same_font_split_header_keeps_all_three_rows_and_metadata(self):
        with TestClient(app) as client:
            response = client.post(
                "/api/extract/structured",
                files={"file": ("same-font-header.pdf", same_font_split_header_pdf(), "application/pdf")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["cliente"], "Cliente Mesmo Fonte")
        rows = body["tabelas"][0]["linhas"]
        self.assertEqual(rows, [
            {"item": "COR", "formula_unid": "kg", "metodo_especif": "VISUAL", "analitico": "11", "observacoes": "OK"},
            {"item": "ASPECTO", "formula_unid": None, "metodo_especif": "FISICO", "analitico": "APROVADO", "observacoes": None},
            {"item": "TEXTURA", "formula_unid": "g", "metodo_especif": "SENSORIAL", "analitico": "CONFORME", "observacoes": None},
        ])
        self.assertEqual(list(rows[0]), FIVE_KEYS)


if __name__ == "__main__":
    unittest.main()
