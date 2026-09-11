"""Recover five-column rows when ruled-cell geometry and header text disagree.

The helper is deliberately independent of the parser.  Callers can use the
returned rows as a replacement only when the document provides enough
alignment evidence; otherwise ``None`` leaves the normal extraction path in
charge.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


CANONICAL_HEADERS = ["ITEM", "UNIDADE", "ESPECIFICACOES", "RESULTADO", "OBSERVACOES"]
CANONICAL_KEYS = ["item", "unidade", "especificacoes", "resultado", "observacoes"]


def _plain(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).upper()


def _bands(chars: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    bands: list[list[dict[str, Any]]] = []
    for char in chars:
        top = float(char.get("top", 0))
        band = next((candidate for candidate in reversed(bands) if abs(float(candidate[0].get("top", 0)) - top) <= 2), None)
        if band is None:
            bands.append([char])
        else:
            band.append(char)
    return sorted(bands, key=lambda band: float(band[0].get("top", 0)))


def _table_rows(table: Any) -> list[Any]:
    return list(getattr(table, "rows", None) or [])


def _row_bbox(row: Any) -> tuple[float, float, float, float] | None:
    bbox = getattr(row, "bbox", None)
    if not bbox or len(bbox) < 4:
        return None
    return tuple(float(value) for value in bbox[:4])  # type: ignore[return-value]


def _header_anchors(page: Any, table: Any) -> tuple[list[float], float] | None:
    chars = list(getattr(page, "chars", None) or [])
    bbox = getattr(table, "bbox", None)
    if not chars or not bbox:
        return None
    _, top, _, bottom = (float(value) for value in bbox[:4])
    # Do not clip by x: malformed grids can place header glyphs outside their
    # ruled cell while the surrounding page still identifies the table.
    scoped = [char for char in chars if top - 2 <= float(char.get("top", 0)) <= bottom + 2]
    bands = _bands(scoped)
    table_rows = _table_rows(table)
    first_rows = [_row_bbox(row) for row in table_rows[:3]]
    first_rows = [row for row in first_rows if row is not None]
    if first_rows:
        header_limit = max(row[3] for row in first_rows)
        bands = [band for band in bands if float(band[0].get("top", 0)) <= header_limit + 2]
    # Header runs may be split over adjacent text bands.  Preserve character
    # positions while examining each band and its immediate continuation.
    for index, band in enumerate(bands):
        candidates = [band]
        if index + 1 < len(bands) and float(bands[index + 1][0].get("top", 0)) - float(band[0].get("top", 0)) <= 24:
            candidates.append(band + bands[index + 1])
        for candidate in candidates:
            ordered = candidate
            normalized_chars: list[str] = []
            source_x: list[float] = []
            for char in ordered:
                normalized = _plain(str(char.get("text", "")))
                normalized_chars.extend(normalized)
                source_x.extend([float(char.get("x0", 0))] * len(normalized))
            text = "".join(normalized_chars)
            anchors: list[float] = []
            cursor = 0
            for pattern in (r"ITEM", r"FORMU(?:LA)?", r"METODO", r"ANALITICO", r"OBSERVA(?:COES)?"):
                match = re.search(pattern, text[cursor:], re.IGNORECASE)
                if match is None:
                    break
                position = cursor + match.start()
                anchors.append(source_x[position])
                cursor = cursor + match.end()
            if len(anchors) == 5 and all(right > left for left, right in zip(anchors, anchors[1:])):
                return anchors, float(band[0].get("top", 0))
    return None


def _grid_starts(table: Any) -> list[float] | None:
    for row in _table_rows(table):
        cells = list(getattr(row, "cells", None) or [])
        starts = [float(cell[0]) for cell in cells if cell is not None and len(cell) >= 4]
        if len(starts) == 5:
            return starts
    return None


def aligned_rows(page: Any, table: Any, rows: list[list[Any]]) -> list[list[Any]] | None:
    """Return physically aligned five-column rows when evidence is sufficient.

    Header anchors are learned from page characters.  At least two data rows
    must contain two distinct words whose header alignment is a better fit than
    the ruled-grid starts.  Returned rows retain all words in order and pad
    empty cells with ``None``.
    """
    if not rows or max((len(row) for row in rows), default=0) != 5:
        return None
    header = _header_anchors(page, table)
    grid = _grid_starts(table)
    table_rows = _table_rows(table)
    if header is None or grid is None or len(table_rows) < 2:
        return None
    anchors, header_top = header
    words = list(page.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["size"]) or [])
    evidence = 0
    output: list[list[Any]] = []
    for index, row in enumerate(rows):
        if index >= len(table_rows):
            continue
        bbox = _row_bbox(table_rows[index])
        if bbox is None or float(bbox[1]) <= header_top:
            continue
        row_words = [word for word in words if bbox[1] <= (float(word.get("top", 0)) + float(word.get("bottom", 0))) / 2 <= bbox[3]]
        if not row_words:
            output.append([None] * 5)
            continue
        aligned = [[] for _ in range(5)]
        matches: set[int] = set()
        anchor_residual = 0.0
        grid_residual = 0.0
        for word in sorted(row_words, key=lambda item: float(item.get("x0", 0))):
            x0 = float(word.get("x0", 0))
            anchor_index = min(range(5), key=lambda position: abs(x0 - anchors[position]))
            grid_index = min(range(5), key=lambda position: abs(x0 - grid[position]))
            font_size = float(word.get("size", 10) or 10)
            anchor_error = abs(x0 - anchors[anchor_index])
            grid_error = abs(x0 - grid[grid_index])
            anchor_residual += anchor_error
            grid_residual += grid_error
            if anchor_index != grid_index and anchor_error <= font_size * 0.6:
                matches.add(anchor_index)
            aligned[anchor_index].append(str(word.get("text", "")))
        if len(matches) >= 2 and anchor_residual < grid_residual:
            evidence += 1
        output.append([" ".join(cell).strip() or None for cell in aligned])
    return [CANONICAL_HEADERS] + output if evidence >= 2 else None
