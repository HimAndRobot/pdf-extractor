"""Conservative extraction of borderless tables from PDF word geometry.

This module intentionally learns column bands from each report's own header.  It
does not contain report coordinates or an item catalogue, and reports uncertain
rows to callers instead of inventing values.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pdfplumber

THREE = ["especificacao", "parametro", "resultado"]
FIVE = ["item", "unidade", "especificacoes", "resultado", "observacao"]
_SECTION = re.compile(r"(?:caracter(?:isticas|ística)|categorias?|ensaios?|an[aá]lises?)\s*[:\-]?\s*(?:organoleptic|organoleptica|fisico|quimic)", re.I)
_FOOTER = re.compile(r"(?:assinatura|respons[aá]vel|elaborado por|conferido por|nome\s*[:.]|cargo\s*[:.])", re.I)


def _fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).lower()


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold(value))


def _clean(value: str) -> str | None:
    value = re.sub(r"\s+", " ", value).strip(" |;\t")
    return value or None


def _lines(words: list[dict[str, Any]], tolerance: float = 2.5) -> list[list[dict[str, Any]]]:
    result: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        line = next((candidate for candidate in reversed(result) if abs(float(candidate[0]["top"]) - top) <= tolerance), None)
        if line is None:
            result.append([word])
        else:
            line.append(word)
    return [sorted(line, key=lambda item: float(item["x0"])) for line in result]


def _header(line: list[dict[str, Any]]) -> tuple[str, list[float]] | None:
    labels = [_norm(str(word.get("text", ""))) for word in line]
    for kind, columns in (("five", FIVE), ("three", THREE)):
        centers: list[float] = []
        used: set[int] = set()
        for column in columns:
            candidates = [index for index, label in enumerate(labels) if index not in used and label == column]
            if not candidates:
                break
            index = candidates[0]
            used.add(index)
            centers.append((float(line[index]["x0"]) + float(line[index]["x1"])) / 2)
        if len(centers) == len(columns):
            return kind, centers
    return None


def _section(line: list[dict[str, Any]]) -> str | None:
    text = _clean(" ".join(str(word.get("text", "")) for word in line))
    if text and (_SECTION.search(_fold(text)) or re.fullmatch(r"(?:organoleptic|organoleptica|fisico.?quimic[ao])", _fold(text))) and len(line) <= 7:
        return text
    return None


def parse_borderless(
    page: pdfplumber.page.Page,
    previous_columns: tuple[str, list[float]] | None = None,
) -> tuple[list[dict[str, Any]], list[str], float | None]:
    """Parse borderless tables on *page* using header-derived x bands.

    Returns ``(tables, warnings, header_top)``. ``previous_columns`` may be a
    ``(kind, centers)`` pair from a prior page when a table continues without a
    repeated header. The caller can pass ``header_top`` to its metadata cutoff.
    """
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    lines = _lines(words)
    warnings: list[str] = []
    tables: list[dict[str, Any]] = []
    header_index: int | None = None
    header_top: float | None = None
    columns: list[str] | None = None
    centers: list[float] | None = None
    kind: str | None = None

    for index, line in enumerate(lines):
        found = _header(line)
        if found:
            kind, centers = found
            columns = FIVE if kind == "five" else THREE
            header_index, header_top = index, float(line[0]["top"])
            break
    if columns is None and previous_columns is not None:
        kind, centers = previous_columns
        columns = FIVE if kind == "five" else THREE
        header_index = -1
    if columns is None or centers is None:
        if any(len(line) >= 3 and " ".join(_norm(str(w.get("text", ""))) for w in line) in {"itemunidaderesultado", "especificacaoparametroresultado"} for line in lines):
            warnings.append("Cabeçalho achatado sem separação suficiente; nenhuma linha foi inferida.")
        return [], warnings, None
    if centers != sorted(centers):
        warnings.append("Cabeçalho com colunas fora da ordem canônica; tabela não foi inferida.")
        return [], warnings, header_top

    # A header whose words are merely space-separated is not enough evidence
    # for column geometry. Real cells leave a materially larger gap than the
    # word spacing inside a label; reject this case so following text cannot be
    # silently turned into invented rows.
    if header_index is not None and header_index >= 0 and len(lines[header_index]) > 1:
        header_line = lines[header_index]
        gaps = [float(right["x0"]) - float(left["x1"]) for left, right in zip(header_line, header_line[1:])]
        heights = [float(word.get("bottom", word["top"])) - float(word["top"]) for word in header_line]
        if gaps and max(gaps) <= max(8.0, (sum(heights) / max(1, len(heights))) * 1.5):
            warnings.append("Cabeçalho achatado sem separação suficiente; nenhuma linha foi inferida.")
            return [], warnings, header_top

    # Midpoints between header centers define bands and preserve arbitrary
    # multiword values in the first and last columns.
    bounds = [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)]
    if any(centers[i + 1] - centers[i] < 12 for i in range(len(centers) - 1)):
        warnings.append("Cabeçalho com separação insuficiente; linhas ambíguas foram preservadas como aviso.")

    section: str | None = None
    if header_index is not None and header_index >= 0:
        for line in reversed(lines[:header_index]):
            prior = _section(line)
            if prior:
                section = prior
                break

    rows: list[dict[str, str | None]] = []
    last_top = header_top or 0
    saw_data = False

    def flush() -> None:
        nonlocal rows
        if rows:
            tables.append({"section": section, "columns": columns, "rows": rows})
            rows = []

    for line in lines[(header_index + 1 if header_index >= 0 else 0) :]:
        top = float(line[0]["top"])
        text = _clean(" ".join(str(word.get("text", "")) for word in line)) or ""
        repeated = _header(line)
        if header_index >= 0 and repeated:
            if repeated[0] == kind:
                kind, centers = repeated
                columns = FIVE if kind == "five" else THREE
                bounds = [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)]
                continue
            flush()
            warnings.append(f"Novo cabeçalho de tabela encontrado após linhas anteriores: {text}")
            kind, centers = repeated
            columns = FIVE if kind == "five" else THREE
            bounds = [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)]
            continue
        if saw_data and top - last_top > 42:
            flush()
            break
        if _FOOTER.search(text):
            flush()
            break
        found_section = _section(line)
        if found_section and len(line) <= 7:
            flush()
            section = found_section
            last_top = top
            continue

        cells: list[list[str]] = [[] for _ in columns]
        # Cluster nearby words first. This keeps labels such as
        # "APARENCIA DO PRODUTO" together even when they cross a midpoint.
        chunks: list[list[dict[str, Any]]] = []
        for word in line:
            if chunks and float(word["x0"]) - float(chunks[-1][-1]["x1"]) <= max(5.0, min(14.0, min((centers[i + 1] - centers[i]) for i in range(len(centers) - 1)) * 0.18)):
                chunks[-1].append(word)
            else:
                chunks.append([word])
        for chunk_index, chunk in enumerate(chunks):
            chunk_start, chunk_end = float(chunk[0]["x0"]), float(chunk[-1]["x1"])
            if len(chunks) == len(columns):
                # When every cell has content, the left-to-right sequence is
                # stronger evidence than a midpoint (wide multiword cells can
                # legitimately extend into a neighboring midpoint).
                index = chunk_index
            elif chunk_start < bounds[0]:
                index = 0
            elif chunk_end > bounds[-1]:
                index = len(centers) - 1
            else:
                x = (chunk_start + chunk_end) / 2
                index = min(range(len(centers)), key=lambda candidate: abs(centers[candidate] - x))
            cells[index].extend(str(word.get("text", "")) for word in chunk)
        values = [_clean(" ".join(cell)) for cell in cells]
        if not any(values):
            continue
        nonempty = sum(value is not None for value in values)
        if nonempty == 1 and not saw_data:
            continue
        if values[0] is None and rows:
            continuation = next((value for value in values[1:] if value), None)
            if continuation:
                warnings.append(f"Linha de continuação ambígua preservada na tabela: {text}")
                previous = rows[-1]
                for column, value in zip(columns[1:], values[1:]):
                    if value:
                        previous[column] = _clean(f"{previous.get(column) or ''} {value}")
                last_top = top
                continue
        if nonempty < 2:
            warnings.append(f"Linha sem separação suficiente preservada como aviso: {text}")
            continue
        rows.append({column: values[index] for index, column in enumerate(columns)})
        saw_data = True
        last_top = top
    flush()
    return tables, warnings, header_top
