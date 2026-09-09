import unittest
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import pdfplumber

from app.structured_generic_geometry import parse_generic_borderless


class Page:
    def __init__(self, rows):
        self.rows = rows

    def extract_words(self, **kwargs):
        words = []
        for top, row in enumerate(self.rows):
            for x, text in row:
                words.append({"text": text, "x0": x, "x1": x + max(8, len(text) * 5), "top": top * 18, "bottom": top * 18 + 10})
        return words


class GenericGeometryTests(unittest.TestCase):
    def test_real_pdf_multiword_headers_and_blank_cell(self):
        out = io.BytesIO(); c = canvas.Canvas(out, pagesize=letter)
        for y, cells in [(720, [(50, "nome do item"), (230, "unidade medida"), (410, "resultado final")]), (700, [(50, "AMOSTRA NOVA"), (410, "12,5")]), (680, [(50, "OUTRA AMOSTRA"), (230, "kg"), (410, "13,0")])]:
            for x, value in cells: c.drawString(x, y, value)
        c.drawString(50, 650, "Texto de rodapé: responsável técnico")
        c.save()
        with pdfplumber.open(io.BytesIO(out.getvalue())) as pdf:
            tables, warnings, _ = parse_generic_borderless(pdf.pages[0])
        self.assertEqual(tables[0]["columns"], ["nome_do_item", "unidade_medida", "resultado_final"])
        self.assertIsNone(tables[0]["rows"][0]["unidade_medida"])
        self.assertEqual(tables[0]["rows"][1]["item"], "OUTRA AMOSTRA") if "item" in tables[0]["rows"][1] else self.assertEqual(tables[0]["rows"][1]["nome_do_item"], "OUTRA AMOSTRA")
    def test_unknown_header_and_dynamic_columns(self):
        page = Page([[ (10, "ATRIBUTO"), (160, "FAIXA"), (310, "LEITURA") ], [(10, "ITEM NOVO"), (160, "10 A 12"), (310, "11,2")], [(10, "OUTRO ITEM"), (310, "-"), (400, "OBS")]])
        tables, warnings, top = parse_generic_borderless(page)
        self.assertEqual(tables[0]["columns"], ["atributo", "faixa", "leitura"])
        self.assertEqual(tables[0]["rows"][0]["atributo"], "ITEM NOVO")
        self.assertIsNone(tables[0]["rows"][1]["faixa"])
        self.assertEqual(top, 0)

    def test_prose_without_header_is_rejected(self):
        tables, warnings, _ = parse_generic_borderless(Page([[(10, "This is ordinary prose without a table")], [(10, "and another sentence")]]))
        self.assertEqual(tables, [])
        self.assertTrue(warnings)

    def test_headerless_aligned_data_keeps_all_rows(self):
        page = Page([[(10, "Primeiro valor"), (160, "Texto livre"), (310, "11")], [(10, "Segundo valor"), (160, "Outro texto"), (310, "22")], [(10, "Terceiro valor"), (160, "Mais texto"), (310, "33")], [(10, "Quarto valor"), (160, "Ultimo texto"), (310, "44")]])
        tables, warnings, _ = parse_generic_borderless(page)
        self.assertEqual(len(tables[0]["rows"]), 4)

    def test_insufficient_header_spacing_warns(self):
        tables, warnings, _ = parse_generic_borderless(Page([[(10, "AAA"), (30, "BBB"), (50, "CCC")], [(10, "one"), (30, "two"), (50, "three")]]))
        self.assertEqual(tables, [])
        self.assertTrue(warnings)

    def test_duplicate_headers_get_unique_keys(self):
        tables, warnings, _ = parse_generic_borderless(Page([[(10, "ITEM"), (160, "ITEM"), (310, "ITEM")], [(10, "A"), (160, "B"), (310, "C")], [(10, "D"), (160, "E"), (310, "F")]]))
        self.assertEqual(tables[0]["columns"], ["item", "item_2", "item_3"])
        self.assertEqual(tables[0]["rows"][0], {"item": "A", "item_2": "B", "item_3": "C"})


if __name__ == "__main__":
    unittest.main()
