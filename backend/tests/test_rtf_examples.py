"""Acceptance coverage for the checked-in native RTF laudo fixtures."""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


class RtfExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def extract(self, filename):
        response = self.client.post(
            "/api/extract/structured",
            files={"file": (filename, (ROOT / "examples" / filename).read_bytes(), "application/rtf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_laudo_241_full_contract(self):
        body = self.extract("Laudo241.322.rtf")
        self.assertEqual({key: body[key] for key in ("produto", "lote", "data_le", "data_fabricacao", "data_validade", "nota_fiscal", "embalagem", "quantidade", "fornecedor", "transportadora")}, {
            "produto": "ESSENCIA DE EUCALIPTO", "lote": "241.322", "data_le": "07.05.12", "data_fabricacao": "08.04.12", "data_validade": "08.05.13", "nota_fiscal": "21899", "embalagem": "FR", "quantidade": "06 KG", "fornecedor": "CAPUANI", "transportadora": "TRANSITO",
        })
        self.assertEqual(body["tabelas"][0]["linhas"], [
            {"item": "ASPECTO", "unidade": None, "especificacoes": None, "resultado": "LIQUIDO", "observacoes": "AMARELADO"},
            {"item": "ODOR", "unidade": None, "especificacoes": None, "resultado": "CARACT", "observacoes": None},
            {"item": "DENSIDADE", "unidade": None, "especificacoes": None, "resultado": "0,9154", "observacoes": None},
            {"item": "IND DE REFRAÇÃO", "unidade": None, "especificacoes": None, "resultado": "1,4476", "observacoes": None},
            {"item": "PONTO FULGOR", "unidade": None, "especificacoes": None, "resultado": "DE ACORDO", "observacoes": None},
        ])

    def test_other_rtf_examples_have_exact_metadata_and_rows(self):
        expectations = {
            "Laudo_N10066.rtf": {
                "meta": ("ALVEJANTE WHITE", "2016/43913", "07/11/2016", "07/11/2016", "1.000,000000 L"),
                "rows": [[{"item": "PH", "unidade": None, "especificacoes": None, "resultado": "4,4", "observacoes": None}, {"item": "TEMP PRODUTO", "unidade": "° C", "especificacoes": None, "resultado": "28,1", "observacoes": None}, {"item": "TEMP AMBIENTE", "unidade": "° C", "especificacoes": None, "resultado": "23,1", "observacoes": None}, {"item": "VISCOSIDADE", "unidade": "S", "especificacoes": None, "resultado": "0,09", "observacoes": None}, {"item": "DENSIDADE", "unidade": "g/ml", "especificacoes": None, "resultado": "1,01", "observacoes": None}, {"item": "COR", "unidade": None, "especificacoes": "WHITE", "resultado": "CONFERE", "observacoes": None}, {"item": "ASPECTO", "unidade": None, "especificacoes": "LIQUIDO", "resultado": "CONFERE", "observacoes": None}]],
            },
            "Laudo_N45637.rtf": {
                "meta": ("CONFORTIN LAC ACIDO", "2022/93596", "28/02/2022", "01/03/2022", "3.000,000000"),
                "rows": [[{"especificacao": "FORMA PRODUTO", "parametro": "LIQ. BAIXA VISCOSIDADE", "resultado": "CONFERE"}, {"especificacao": "COR", "parametro": "INCOLOR", "resultado": "CONFERE"}, {"especificacao": "ODOR", "parametro": "CARACTERISTICO", "resultado": "CONFERE"}], [{"especificacao": "DENSIDADE G/ML", "parametro": "1,08 A 1,15", "resultado": "1,15"}, {"especificacao": "VISCOSIDADE(S)", "parametro": "8 A 12 SEGUNDOS", "resultado": "8,0"}, {"especificacao": "PH PURO", "parametro": "0 A 2", "resultado": "0,0"}, {"especificacao": "TEMPERATURA PRODUTO ºC", "parametro": "15 A 30", "resultado": "24,9"}, {"especificacao": "TEMPERATURA AMBIENTE ºC", "parametro": "15 A 30", "resultado": "25,8"}]],
            },
            "Laudo_N67278.rtf": {
                "meta": ("MAX COMPACT 300CP - 200 KG", "2025/128158", "20/08/2025", "20/08/2025", "10 UND"),
                "rows": [[{"especificacao": "FORMA PRODUTO", "parametro": "LIQUIDO VISCOSO", "resultado": "CONFERE"}, {"especificacao": "COR", "parametro": "AZUL", "resultado": "CONFERE"}, {"especificacao": "ODOR", "parametro": "CARACTERISTICO", "resultado": "CONFERE"}], [{"especificacao": "DENSIDADE G/ML", "parametro": "1,02 A 1,04", "resultado": "1,03"}, {"especificacao": "VISCOSIDADE(S)", "parametro": "1min A 1min 30segundos", "resultado": "1:13"}, {"especificacao": "PH PURO", "parametro": "8,5 A 9,5", "resultado": "8,7"}, {"especificacao": "TEMPERATURA PRODUTO ºC", "parametro": "15 A 30", "resultado": "21,3"}, {"especificacao": "TEMPERATURA AMBIENTE ºC", "parametro": "15 A 30", "resultado": "21,1"}]],
            },
        }
        for filename, expectation in expectations.items():
            with self.subTest(filename=filename):
                body = self.extract(filename)
                produto, lote, data_le, fabricacao, quantidade = expectation["meta"]
                self.assertEqual(body["produto"], produto)
                self.assertEqual(body["lote"], lote)
                self.assertEqual(body["data_le"], data_le)
                self.assertEqual(body["data_fabricacao"], fabricacao)
                self.assertEqual(body["quantidade"], quantidade)
                self.assertEqual([table["linhas"] for table in body["tabelas"]], expectation["rows"])


if __name__ == "__main__":
    unittest.main()
