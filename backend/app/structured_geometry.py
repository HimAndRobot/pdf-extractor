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
FIVE = ["item", "formula_unid", "metodo_especif", "analitico", "observacoes"]
_OLD_FIVE = ["item", "unidade", "especificacoes", "resultado", "observacao"]
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
    # Adjacent glyph fragments in one physical cell (e.g. OBSERVA + COES)
    # form one header token. Keep the x span for the resulting band center.
    merged: list[dict[str, Any]] = []
    for word in line:
        if merged and float(word["x0"]) - float(merged[-1]["x1"]) <= 14:
            merged[-1] = {**merged[-1], "text": f"{merged[-1]['text']} {word.get('text', '')}", "x1": word["x1"]}
        else:
            merged.append(dict(word))
    line = merged
    labels = [_norm(str(word.get("text", ""))) for word in line]
    if len(labels) == 5 and set(labels) == set(_OLD_FIVE):
        return "five", [(float(word["x0"]) + float(word["x1"])) / 2 for word in line]
    for kind, columns in (("five", _OLD_FIVE), ("three", THREE)):
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
    # A physically separated five-cell header remains authoritative even when
    # every label is split, reordered, or nonsense.  Geometry supplies the
    # semantics; text is only used to establish that this is a header-like row.
    if len(line) == 5:
        gaps = [float(right["x0"]) - float(left["x1"]) for left, right in zip(line, line[1:])]
        fontnames = " ".join(str(word.get("fontname", "")) for word in line).lower()
        if all(gap >= 18 for gap in gaps) and all(re.search(r"[A-Za-zÀ-ÿ]", label) for label in labels):
            return "five", [(float(word["x0"]) + float(word["x1"])) / 2 for word in line]
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
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["fontname", "size"])
    lines = _lines(words)
    warnings: list[str] = []
    tables: list[dict[str, Any]] = []
    header_index: int | None = None
    header_end_index: int | None = None
    header_top: float | None = None
    columns: list[str] | None = None
    centers: list[float] | None = None
    kind: str | None = None

    for index, line in enumerate(lines):
        found = _header(line)
        known_header = len(line) == 5 and set(_norm(str(word.get("text", ""))) for word in line) == set(_OLD_FIVE)
        if found and found[0] == "five" and not known_header and not ("bold" in " ".join(str(word.get("fontname", "")) for word in line).lower()):
            # Nonsense headers need visual evidence against headerless data.
            following = lines[index + 1] if index + 1 < len(lines) else []
            current_size = max((float(word.get("size", 0) or 0) for word in line), default=0)
            following_size = max((float(word.get("size", 0) or 0) for word in following), default=0)
            first_bound = (float(found[1][0]) + float(found[1][1])) / 2 if found and len(found[1]) > 1 else float(line[0]["x0"]) + 40
            continuation_shape = bool(following and len(following) <= 3 and float(following[0]["x0"]) > first_bound)
            if not following or (current_size <= following_size and not continuation_shape):
                found = None
            elif continuation_shape:
                header_end_index = index + 1
        if not found and index + 1 < len(lines) and float(lines[index + 1][0]["top"]) - float(line[0]["top"]) <= 24:
            # Some producers put only three header cells on the first line and
            # the remaining two cells on a continuation line. Infer bands from
            # the combined physical x positions before falling back to text.
            combined = sorted(line + lines[index + 1], key=lambda word: float(word["x0"]))
            if len(combined) == 5:
                found = _header(combined)
                if found:
                    header_end_index = index + 1
        if found:
            kind, centers = found
            columns = FIVE if kind == "five" else THREE
            header_index, header_top = index, float(line[0]["top"])
            if header_end_index is None:
                header_end_index = index
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

    start_index = header_end_index + 1 if header_end_index is not None and header_end_index >= 0 else (header_index + 1 if header_index >= 0 else 0)
    for line in lines[start_index:]:
        top = float(line[0]["top"])
        text = _clean(" ".join(str(word.get("text", "")) for word in line)) or ""
        repeated = _header(line)
        # Geometry-only five detection is intentionally conservative after the
        # first header: ordinary five-word data rows are not headers.
        if repeated and repeated[0] == "five":
            markers = sum(_norm(str(word.get("text", ""))) in {"item", "formula", "formu", "unid", "metodo", "especif", "analitico", "observa", "observacoes"} for word in line)
            if markers < 2:
                repeated = None
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
        # A second line containing fragments of a multi-line header must not
        # become a data row.  Once actual data starts, sparse rows are kept.
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
