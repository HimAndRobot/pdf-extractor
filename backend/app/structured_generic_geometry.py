"""Conservative geometry extraction for tables with unfamiliar headers."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _clean(s: str | None) -> str | None:
    if not s:
        return None
    value = re.sub(r"\s+", " ", s).strip(" |;\t")
    return value or None


def _lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    result: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        line = next((line for line in reversed(result) if abs(float(line[0]["top"]) - float(word["top"])) <= 2.5), None)
        if line is None:
            result.append([word])
        else:
            line.append(word)
    return [sorted(line, key=lambda w: float(w["x0"])) for line in result]


def _chunks(line: list[dict[str, Any]], gap: float = 16) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for word in line:
        if chunks and float(word["x0"]) - float(chunks[-1]["x1"]) <= gap:
            chunks[-1]["text"] += " " + str(word.get("text", "")); chunks[-1]["x1"] = word["x1"]
        else:
            chunks.append({"text": str(word.get("text", "")), "x0": word["x0"], "x1": word["x1"]})
    return chunks


def _header(line: list[dict[str, Any]]) -> tuple[list[str], list[float]] | None:
    chunks = _chunks(line)
    if len(chunks) < 3 or len(chunks) > 8:
        return None
    labels = [_clean(str(w.get("text", ""))) for w in chunks]
    if any(not x or not re.search(r"[A-Za-zÀ-ÿ]", x) for x in labels):
        return None
    gaps = [float(chunks[i + 1]["x0"]) - float(chunks[i]["x1"]) for i in range(len(chunks) - 1)]
    if not gaps or sum(g > 10 for g in gaps) < len(gaps) - 1:
        return None
    return [x or "" for x in labels], [(float(w["x0"]) + float(w["x1"])) / 2 for w in chunks]


def parse_generic_borderless(page: Any) -> tuple[list[dict[str, Any]], list[str], float | None]:
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    lines = _lines(words)
    warnings: list[str] = []
    # Metadata rows can have three widely spaced labels but are not table headers.
    header_index = next((i for i, line in enumerate(lines) if _header(line) and not any(":" in str(w.get("text", "")) for w in line)), None)
    if header_index is None:
        # Headerless aligned data is retained only when two consecutive lines
        # exhibit the same three-or-more chunk structure.
        for i in range(max(0, len(lines) - 1)):
            candidates = [_chunks(lines[j]) for j in (i, i + 1)]
            if any(":" in str(chunk.get("text", "")) for chunks in candidates for chunk in chunks):
                continue
            if all(3 <= len(chunks) <= 8 for chunks in candidates):
                width = len(candidates[0])
                if len(candidates[1]) == width:
                    columns = [f"coluna_{n + 1}" for n in range(width)]
                    anchors = [float(candidates[0][n]["x0"]) for n in range(width)]
                    rows = []
                    for line in lines[i:]:
                        chunks = _chunks(line)
                        if len(chunks) != width or any(abs(float(chunks[n]["x0"]) - anchors[n]) > 14 for n in range(width)):
                            break
                        rows.append({col: _clean(chunks[n]["text"]) for n, col in enumerate(columns)})
                    if len(rows) >= 2:
                        return [{"section": None, "columns": columns, "rows": rows}], ["Nenhum cabeçalho foi identificado; colunas genéricas foram usadas."], float(lines[i][0]["top"])
        return [], ["Não foi possível inferir colunas para a tabela desconhecida."], None
    header, centers = _header(lines[header_index])  # type: ignore[misc]
    evidence_words = ("item", "nome", "unidade", "resultado", "observacao", "especific", "param", "atribut", "faixa", "leitura", "metodo", "formula")
    evidence = sum(any(token in _fold(label) for token in evidence_words) for label in header)
    neutral = evidence < 2
    columns = [re.sub(r"[^a-z0-9]+", "_", _fold(x)).strip("_") or f"coluna_{i + 1}" for i, x in enumerate(header)] if not neutral else [f"coluna_{i + 1}" for i in range(len(header))]
    # Duplicate/empty labels remain addressable and do not overwrite each other.
    used: set[str] = set()
    for i, col in enumerate(columns):
        base = col; suffix = 1
        while col in used:
            suffix += 1; col = f"{base}_{suffix}"
        columns[i] = col; used.add(col)
    bounds = [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)]
    if min((centers[i + 1] - centers[i] for i in range(len(centers) - 1)), default=0) < 18:
        return [], ["As colunas da tabela desconhecida estão demasiado próximas para uma extração segura."], float(lines[header_index][0]["top"])
    rows: list[dict[str, str | None]] = []
    if neutral:
        rows.append({column: header[i] for i, column in enumerate(columns)})
    for line in lines[header_index + 1 :]:
        text = _clean(" ".join(str(w.get("text", "")) for w in line)) or ""
        if re.search(r"(?i)(assinatura|respons[aá]vel|elaborado por|supervis[aã]o|este certificado|farmac[eê]utica|qu[ií]mico)", text):
            break
        if len(line) <= 2 and not rows:
            continue
        cells: list[list[str]] = [[] for _ in columns]
        for word in _chunks(line):
            x = (float(word["x0"]) + float(word["x1"])) / 2
            cells[sum(x >= bound for bound in bounds)].append(str(word.get("text", "")))
        values = [_clean(" ".join(cell)) for cell in cells]
        if sum(v is not None for v in values) < 2:
            if rows:
                warnings.append(f"Linha ambígua preservada como aviso: {text}")
            continue
        rows.append({column: values[i] for i, column in enumerate(columns)})
    if len(rows) < 2:
        warnings.append("A tabela desconhecida não tem linhas alinhadas suficientes para confirmação.")
        return [], warnings, float(lines[header_index][0]["top"])
    if not rows:
        warnings.append("Nenhuma linha suficientemente separada foi encontrada na tabela desconhecida.")
        return [], warnings, float(lines[header_index][0]["top"])
    return [{"section": None, "columns": columns, "rows": rows}], warnings, float(lines[header_index][0]["top"])
