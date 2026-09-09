import unittest

from app.structured_parser import metadata


class MetadataBoundaryTests(unittest.TestCase):
    def test_flattened_unknown_header_and_footer_do_not_pollute_client(self):
        snippet = (
            "CLIENTE: LATICINIOS KIFORMAGGIO LTDA ITEM FORMULA UMNEIDTO. DO ESPECIFA. "
            "NALITICOO BSERVACOES ASPECTO LIQUIDO OK COR AMARELADO OK ODOR CARACTETISTICO OK "
            "DENSIDADE 1,32-1,34 1,33 CONCENTRACAO MIN 53 53,20 Este certificado esta baseado "
            "nas informações do fabricante. Cabe a Reinigend Quimica do Brasil Ltda responsabilizar-se "
            "pelas informações. DR. LUSANDRO ANDRE HICKMANN QUIMICO RESPONSAVEL CRQ 05201112 - V REGIÃO "
            "ANDRE KOLLING - CRQ 05101554 - V REGIÃO SUPERVISÃO E RESPONSABILIDADE TECNICA"
        )
        self.assertEqual(metadata(snippet)["cliente"], "LATICINIOS KIFORMAGGIO LTDA")

    def test_newline_variant_stops_at_contextual_header(self):
        value = "CLIENTE: LATICINIOS KIFORMAGGIO LTDA\nITEM FORMULA UMNEIDTO. DO ESPECIFA. NALITICOO BSERVACOES\nCOR AZUL OK"
        self.assertEqual(metadata(value)["cliente"], "LATICINIOS KIFORMAGGIO LTDA")

    def test_single_company_words_do_not_trigger_boundary(self):
        self.assertEqual(metadata("CLIENTE: ITEM FORMULA CONSULTORIA LTDA")["cliente"], "ITEM FORMULA CONSULTORIA LTDA")

    def test_repeated_formula_words_do_not_trigger_boundary(self):
        self.assertEqual(metadata("PRODUTO: FORMULA FORMULA FORMULA CLIENTE: Fábrica Alfa")["cliente"], "Fábrica Alfa")

    def test_company_with_formula_and_observacoes_is_preserved(self):
        self.assertEqual(metadata("CLIENTE: FORMULA ESPECIAL OBSERVACOES LTDA")["cliente"], "FORMULA ESPECIAL OBSERVACOES LTDA")

    def test_unknown_item_formula_espec_header_is_a_boundary(self):
        value = "CLIENTE: Empresa Alfa ITEM FORMULA ESPECIF. NALITICO OBSERVACOES\nCOR AZUL OK"
        self.assertEqual(metadata(value)["cliente"], "Empresa Alfa")

    def test_footer_alone_stops_value(self):
        self.assertEqual(metadata("CLIENTE: Cliente Alfa Este certificado esta baseado nas informações do fabricante.")["cliente"], "Cliente Alfa")


if __name__ == "__main__":
    unittest.main()
