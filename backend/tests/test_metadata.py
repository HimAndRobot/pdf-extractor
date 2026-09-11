import unittest

from app.structured_parser import key, metadata


class MetadataTests(unittest.TestCase):
    def test_stops_at_accented_table_section_and_preserves_blank_adjacent_field(self):
        result = metadata(
            "PRODUTO: X\nCLIENTE:\nCARACTERÍSTICAS ORGANOLÉPTICAS\n"
            "ESPECIFICAÇÃO PARÂMETRO RESULTADO\nCOR AZUL OK"
        )
        self.assertEqual(result["produto"], "X")
        self.assertIsNone(result["cliente"])

    def test_accepts_common_date_and_invoice_aliases(self):
        result = metadata("Data fab.: 01/01/2025 Data de validade: 01/01/2026 N.F.: 12")
        self.assertEqual(result["data_fabricacao"], "01/01/2025")
        self.assertEqual(result["data_validade"], "01/01/2026")
        self.assertEqual(result["nota_fiscal"], "12")

    def test_label_boundary_does_not_match_subproduto(self):
        result = metadata("SUBPRODUTO: ABC PRODUTO: Válido")
        self.assertEqual(result["produto"], "Válido")

    def test_key_normalizes_accents_and_punctuation(self):
        self.assertEqual(key("Data:"), "data_le")
        self.assertEqual(key("N.F."), "nota_fiscal")


if __name__ == "__main__":
    unittest.main()
