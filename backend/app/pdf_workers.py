"""Top-level process-pool worker functions (spawn safe and picklable)."""
import io
from pypdf import PdfReader
from .rtf_processing import is_rtf


class PdfProcessingError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(status, detail); self.status = status; self.detail = detail


def process_pdf(kind: str, raw: bytes) -> dict:
    if kind not in ("text", "structured"):
        raise PdfProcessingError(500, "Modo de extração inválido.")
    is_pdf = raw.startswith(b"%PDF-")
    is_rtf_content = is_rtf(raw)
    if not (is_pdf or is_rtf_content):
        raise PdfProcessingError(415, "O arquivo enviado não é um PDF ou RTF válido.")
    if is_rtf_content:
        try:
            from .rtf_processing import parse_rtf
            page_count, text, fields, tables, warnings = parse_rtf(raw)
            if kind == "structured":
                return {"page_count": page_count, "fields": fields, "tables": tables, "warnings": warnings, "text": text}
            return {"page_count": page_count, "text": text, "pages": [{"page": 1, "text": text}]}
        except PdfProcessingError:
            raise
        except Exception as exc:
            raise PdfProcessingError(422, "Não foi possível interpretar este RTF.") from exc
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise PdfProcessingError(422, "PDF protegido por senha não é suportado.")
        if kind == "structured":
            from .structured_parser import parse
            page_count, text, fields, tables, warnings = parse(raw)
            if not text:
                raise PdfProcessingError(422, "Este PDF não possui texto selecionável. PDFs digitalizados precisam de OCR.")
            return {"page_count": page_count, "fields": fields, "tables": tables, "warnings": warnings, "text": text}
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except PdfProcessingError:
        raise
    except Exception as exc:
        raise PdfProcessingError(422, "Não foi possível interpretar este PDF.") from exc
    text = "\n\n".join(x for x in pages if x).strip()
    if not text:
        raise PdfProcessingError(422, "Este PDF não possui texto selecionável. PDFs digitalizados precisam de OCR.")
    return {"page_count": len(pages), "text": text, "pages": [{"page": i + 1, "text": x} for i, x in enumerate(pages)]}
