"""Bounded concurrency regression tests for the PDF endpoints.

The fixture is generated in memory and deliberately does not model a private
customer document.  These tests check API behavior under moderate overlap;
they are not a production capacity benchmark.
"""

import io
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.main import app


def multipage_pdf() -> bytes:
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=letter)
    for page in range(4):
        pdf.setFont("Helvetica", 10)
        pdf.drawString(35, 760, f"PRODUTO: Carga {page}")
        pdf.drawString(35, 740, "CLIENTE: Oficina de Teste")
        for x, value in zip((35, 220, 390), ("ESPECIFICACAO", "PARAMETRO", "RESULTADO")):
            pdf.drawString(x, 720, value)
        for x, value in zip((35, 220, 390), ("COR", "AZUL", "APROVADO")):
            pdf.drawString(x, 700, value)
        pdf.showPage()
    pdf.save()
    return out.getvalue()


class ConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = multipage_pdf()

    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def _post(self, endpoint: str, index: int):
        response = self.client.post(
            endpoint,
            files={"file": (f"load-{index}.pdf", self.pdf, "application/pdf")},
        )
        return response.status_code, response.json()

    def _run_batch(self, endpoint: str):
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(self._post, endpoint, index) for index in range(20)]
            # Health must remain available while extraction work is in flight.
            time.sleep(0.01)
            health = []
            for _ in range(3):
                health_started = time.perf_counter()
                health_response = self.client.get("/api/health")
                health.append((health_response.status_code, time.perf_counter() - health_started))
            results = [future.result() for future in futures]
        return (time.perf_counter() - started), health, results

    def test_twenty_legacy_uploads_complete_and_health_stays_available(self):
        elapsed, health, results = self._run_batch("/api/extract")
        self.assertTrue(all(status == 200 and elapsed < 1 for status, elapsed in health), health)
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertTrue(all(body["page_count"] == 4 for _, body in results))
        self.assertLess(elapsed, 60)

    def test_twenty_structured_uploads_complete_and_keep_contract(self):
        elapsed, health, results = self._run_batch("/api/extract/structured")
        self.assertTrue(all(status == 200 and elapsed < 1 for status, elapsed in health), health)
        self.assertTrue(all(status == 200 for status, _ in results))
        for _, body in results:
            self.assertEqual(set(body), {
                "produto", "lote", "data", "nota_fiscal", "data_fabricacao",
                "data_validade", "embalagem", "quantidade", "fornecedor",
                "transportadora", "cliente", "tabelas",
            })
            self.assertEqual(sum(len(table["linhas"]) for table in body["tabelas"]), 4)
            self.assertTrue(all(line.get("especificacao") == "COR" for table in body["tabelas"] for line in table["linhas"]))
        self.assertLess(elapsed, 60)


if __name__ == "__main__":
    unittest.main()
