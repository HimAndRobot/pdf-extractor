import io
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.main import MAX_FILE_SIZE, app


def pdf_bytes(text: str = "Texto selecionável") -> bytes:
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    c.drawString(72, 720, text)
    c.save()
    return out.getvalue()


class ApiRegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_docs_and_openapi(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/docs").status_code, 200)
        spec = self.client.get("/openapi.json")
        self.assertEqual(spec.status_code, 200)
        self.assertIn("/api/extract/structured", spec.json()["paths"])

    def test_legacy_extract_and_exports(self):
        raw = (Path(__file__).parents[2] / "examples" / "laudo.pdf").read_bytes()
        response = self.client.post("/api/extract", files={"file": ("laudo.pdf", raw, "application/pdf")})
        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertIn("REINI SUN", document["text"])
        for endpoint, media in (("/api/export/txt", "text/plain"), ("/api/export/json", "application/json"), ("/api/export/pdf", "application/pdf")):
            exported = self.client.post(endpoint, json=document)
            self.assertEqual(exported.status_code, 200)
            self.assertTrue(exported.headers["content-type"].startswith(media))
            self.assertGreater(len(exported.content), 20)

    def test_structured_encrypted_pdf_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=letter[0], height=letter[1])
        writer.encrypt("secret")
        out = io.BytesIO(); writer.write(out)
        response = self.client.post("/api/extract/structured", files={"file": ("locked.pdf", out.getvalue(), "application/pdf")})
        self.assertEqual(response.status_code, 422)
        self.assertIn("senha", response.json()["detail"].lower())

    def test_size_extension_signature_and_malformed_errors(self):
        with patch("app.main.MAX_FILE_SIZE", 10):
            response = self.client.post("/api/extract/structured", files={"file": ("large.pdf", b"%PDF-" + b"x" * 20, "application/pdf")})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.client.post("/api/extract/structured", files={"file": ("x.txt", b"x", "text/plain")}).status_code, 415)
        self.assertEqual(self.client.post("/api/extract/structured", files={"file": ("x.pdf", b"plain", "application/pdf")}).status_code, 415)
        self.assertEqual(self.client.post("/api/extract/structured", files={"file": ("x.pdf", b"%PDF-not-valid", "application/pdf")}).status_code, 422)

    def test_unknown_selectable_text_returns_warning(self):
        response = self.client.post("/api/extract/structured", files={"file": ("unknown.pdf", pdf_bytes("Documento sem cabeçalho de tabela"), "application/pdf")})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["tables"], [])
        self.assertTrue(body["warnings"])


if __name__ == "__main__":
    unittest.main()
