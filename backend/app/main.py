import io
import json
import re
import asyncio
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from xml.sax.saxutils import escape
from .structured_parser import parse as parse_structured_pdf

MAX_FILE_SIZE = 25 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

app = FastAPI(title="PDF Extractor API", version="1.0.0", docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class PageContent(BaseModel):
    page: int = Field(ge=1)
    text: str


class ExtractedDocument(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    page_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    text: str = Field(max_length=5_000_000)
    pages: list[PageContent] = Field(default_factory=list, max_length=10_000)


class StructuredTable(BaseModel):
    section: str | None = None
    columns: list[str]
    rows: list[dict[str, str | None]]


class StructuredDocument(BaseModel):
    schema_version: str = "1.0"
    filename: str
    page_count: int
    document_type: str = "laudo"
    fields: dict[str, str | None]
    tables: list[StructuredTable]
    warnings: list[str]


async def read_limited(upload: UploadFile) -> bytes:
    data = bytearray()
    while chunk := await upload.read(CHUNK_SIZE):
        data.extend(chunk)
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="O PDF ultrapassa o limite de 25 MB.")
    return bytes(data)


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"[^\w\-. ]+", "", stem, flags=re.UNICODE).strip(" .")
    return cleaned[:120] or "documento"


def attachment_header(filename: str) -> dict[str, str]:
    ascii_name = filename.encode("ascii", "ignore").decode() or "documento"
    return {"Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}



@app.post("/api/extract", response_model=ExtractedDocument)
async def extract_pdf(file: Annotated[UploadFile, File(description="Arquivo PDF")]):
    filename = file.filename or "documento.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Envie um arquivo no formato PDF.")

    raw = await read_limited(file)
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="O arquivo enviado não é um PDF válido.")

    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            try:
                if reader.decrypt("") == 0:
                    raise HTTPException(status_code=422, detail="PDF protegido por senha não é suportado.")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=422, detail="PDF protegido por senha não é suportado.") from exc

        pages: list[PageContent] = []
        for index, page in enumerate(reader.pages, start=1):
            page_text = (page.extract_text() or "").strip()
            pages.append(PageContent(page=index, text=page_text))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Não foi possível interpretar este PDF.") from exc

    text = "\n\n".join(page.text for page in pages if page.text).strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Este PDF não possui texto selecionável. PDFs digitalizados precisam de OCR.",
        )

    return ExtractedDocument(
        filename=filename,
        page_count=len(pages),
        word_count=len(text.split()),
        character_count=len(text),
        text=text,
        pages=pages,
    )


@app.post("/api/extract/structured", response_model=StructuredDocument)
async def extract_structured(file: Annotated[UploadFile, File(description="Arquivo PDF")]):
    filename = file.filename or "documento.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Envie um arquivo no formato PDF.")
    raw = await read_limited(file)
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="O arquivo enviado não é um PDF válido.")
    try:
        # pypdf gives a stable password check; pdfplumber's exception varies by version.
        probe = PdfReader(io.BytesIO(raw), strict=False)
        if probe.is_encrypted and probe.decrypt("") == 0:
            raise ValueError("password")
        page_count, text, fields, tables, warnings = await asyncio.to_thread(parse_structured_pdf, raw)
    except ValueError as exc:
        if str(exc) == "password":
            raise HTTPException(status_code=422, detail="PDF protegido por senha não é suportado.") from exc
        raise HTTPException(status_code=422, detail="Não foi possível interpretar este PDF.") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Não foi possível interpretar este PDF.") from exc
    if not text:
        raise HTTPException(status_code=422, detail="Este PDF não possui texto selecionável. PDFs digitalizados precisam de OCR.")
    return StructuredDocument(
        schema_version="1.0", filename=filename, page_count=page_count,
        document_type="laudo", fields=fields, tables=tables, warnings=warnings,
    )


@app.post("/api/export/txt")
def export_txt(document: ExtractedDocument) -> Response:
    filename = f"{safe_stem(document.filename)}.txt"
    return Response(
        content=document.text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers=attachment_header(filename),
    )


@app.post("/api/export/json")
def export_json(document: ExtractedDocument) -> Response:
    filename = f"{safe_stem(document.filename)}.json"
    payload = document.model_dump()
    payload["word_count"] = len(document.text.split())
    payload["character_count"] = len(document.text)
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers=attachment_header(filename),
    )


def register_font() -> str:
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    if font_path.exists():
        if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("DejaVu", str(font_path)))
        return "DejaVu"
    return "Helvetica"


def add_page_number(canvas, document) -> None:
    canvas.saveState()
    canvas.setFillColorRGB(0.43, 0.49, 0.46)
    canvas.setFont(register_font(), 8)
    canvas.drawCentredString(A4[0] / 2, 13 * mm, f"Página {document.page}")
    canvas.restoreState()


@app.post("/api/export/pdf")
def export_pdf(document: ExtractedDocument) -> StreamingResponse:
    buffer = io.BytesIO()
    font = register_font()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=22 * mm,
        leftMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=22 * mm,
        title=safe_stem(document.filename),
        author="PDF Extractor",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocumentTitle",
        parent=styles["Title"],
        fontName=font,
        fontSize=20,
        leading=25,
        textColor="#14231d",
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )
    body_style = ParagraphStyle(
        "DocumentBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=10.5,
        leading=16,
        textColor="#2f4038",
        spaceAfter=4 * mm,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=body_style,
        fontSize=8.5,
        textColor="#718079",
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )

    story = [
        Paragraph(escape(safe_stem(document.filename)), title_style),
        Paragraph(
            f"Texto extraído pelo PDF Extractor · {len(document.text.split()):,} palavras",
            meta_style,
        ),
        Spacer(1, 2 * mm),
    ]
    paragraphs = re.split(r"\n\s*\n", document.text.strip())
    for index, paragraph in enumerate(paragraphs):
        lines = "<br/>".join(escape(line) for line in paragraph.splitlines())
        if lines:
            story.append(Paragraph(lines, body_style))
        if index and index % 80 == 0:
            story.append(PageBreak())

    pdf.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    buffer.seek(0)
    filename = f"{safe_stem(document.filename)}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers=attachment_header(filename),
    )
