"""Small, dependency free RTF reader for text and table extraction.

RTF has no page model, so callers expose one logical page containing the
document.  Table cells are taken from the author's explicit ``\\cell`` and
``\\row`` markers; whitespace is never used to guess columns.
"""
from __future__ import annotations

import re
from typing import Any

from .structured_parser import CANONICAL_FIELDS, clean, fold, header_kind, metadata, _generic_table

_SKIP_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer",
    "footnote", "annotation", "xmlnstbl", "listtable", "listoverridetable", "themedata", "datastore",
}
_CONTROL_RE = re.compile(r"([a-zA-Z]+)(-?\d+)? ?")

def is_rtf(raw: bytes) -> bool:
    return bool(re.match(rb"^\s*\{\\rtf\d+(?:[\\\s{}]|$)", raw[:128], re.I))

def _fix_surrogates(value: str) -> str:
    return value.encode("utf-16", "surrogatepass").decode("utf-16")


def _parse(raw: bytes) -> tuple[str, list[list[str | None]]]:
    if not is_rtf(raw):
        raise ValueError("RTF header ausente")
    source = raw.decode("cp1252", "replace")
    codepage = re.search(r"\\ansicpg(\d+)", source[:256], re.I)
    if codepage and codepage.group(1) != "1252":
        raise ValueError("Página de código RTF não suportada")
    stack: list[bool] = [False]
    uc_stack: list[int] = [1]
    in_table = False
    rows: list[list[str | None]] = []
    row: list[str | None] = []
    cell: list[str] = []
    plain: list[str] = []
    uc = 1
    skip_fallback = 0
    depth = 0
    i = 0

    def emit(value: str) -> None:
        nonlocal skip_fallback
        if stack[-1]: return
        if skip_fallback:
            skip_fallback -= len(value)
            return
        plain.append(value)
        if in_table: cell.append(value)

    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
            stack.append(stack[-1]); i += 1
            uc_stack.append(uc)
            # A destination is identified by the first control word in a group.
            j = i
            while j < len(source) and source[j] in "\r\n \t": j += 1
            if j < len(source) and source[j] == "\\":
                m = re.match(r"\\\*?([a-zA-Z]+)", source[j:])
                if source[j:j+2] == r"\*" or (m and m.group(1).lower() in _SKIP_DESTINATIONS):
                    stack[-1] = True
            continue
        if ch == "}":
            depth -= 1
            if depth < 0: raise ValueError("RTF com grupos inválidos")
            if len(stack) > 1: stack.pop()
            if len(uc_stack) > 1: uc = uc_stack.pop()
            i += 1; continue
        if ch != "\\":
            if ch not in "\r\n": emit(ch)
            i += 1; continue
        i += 1
        if i >= len(source): break
        if source[i] in "\\{}": emit(source[i]); i += 1; continue
        if source[i] == "'" and i + 2 < len(source):
            try: emit(bytes.fromhex(source[i+1:i+3]).decode("cp1252"))
            except (ValueError, UnicodeDecodeError): pass
            i += 3; continue
        if source[i] == "*": i += 1; continue
        m = _CONTROL_RE.match(source, i)
        if not m:
            i += 1; continue
        word, arg = m.group(1).lower(), m.group(2)
        i = m.end()
        number = int(arg) if arg else None
        if word == "uc" and number is not None: uc = max(0, number)
        elif word == "u" and number is not None:
            if not stack[-1]:
                emit(chr(number if number >= 0 else number + 65536)); skip_fallback = uc
        elif word == "bin" and number is not None:
            if i + max(0, number) > len(source): raise ValueError("RTF binário truncado")
            i = min(len(source), i + max(0, number))
        elif word in ("cell", "nestcell") and not stack[-1]:
            row.append(clean("".join(cell))); cell.clear()
            plain.append("\t")
        elif word in ("row", "nestrow") and not stack[-1]:
            if cell: row.append(clean("".join(cell))); cell.clear()
            if row: rows.append(row); row = []
            plain.append("\n")
            in_table = False
        elif word == "trowd" and not stack[-1]: in_table = True
        elif word == "intbl" and not stack[-1]: in_table = True
        elif word in ("par", "line") and not stack[-1]:
            emit("\n")
        elif word == "tab" and not stack[-1]: emit("\t")
    if depth != 0: raise ValueError("RTF incompleto")
    text = _fix_surrogates("".join(plain))
    rows = [[_fix_surrogates(v) if v is not None else None for v in r] for r in rows]
    text = text.replace("\n\n", "\n")
    return text.strip(), rows


def parse_rtf(raw: bytes) -> tuple[int, str, dict[str, str | None], list[dict[str, Any]], list[str]]:
    text, rows = _parse(raw)
    if not text: raise ValueError("RTF sem texto")
    fields = metadata(text)
    normalized_rows: list[list[str | None]] = []
    for r in rows:
        normalized_rows.append(r)
    rows = [r for r in normalized_rows if any(r)]
    tables: list[dict[str, Any]] = []
    warnings: list[str] = []
    # Preserve explicit rows and map recognized headers by physical position.
    current: list[list[str | None]] = []
    def flush() -> None:
        nonlocal current
        if not current: return
        kind = next((header_kind(r) for r in current if header_kind(r)), None)
        if kind is None and current and len(current[0]) >= 5: kind = "five"
        if kind:
            cols = ["especificacao", "parametro", "resultado"] if kind == "three" else ["item", "unidade", "especificacoes", "resultado", "observacoes"]
            started = False
            section = next((next((v for v in r if v), None) for r in current if sum(v is not None for v in r) == 1 and r[0] and fold(r[0]).startswith("caracteristicas")), None)
            active_section = section
            pending_rows: list[dict[str, str | None]] = []
            def save_rows() -> None:
                nonlocal pending_rows
                if pending_rows:
                    tables.append({"section": active_section, "columns": cols, "rows": pending_rows})
                    pending_rows = []
            for r in current:
                if header_kind(r) == kind: started = True; continue
                if kind == "five" and r and fold(r[0] or "").startswith("item") and len(r) >= 5: started = True; continue
                if not started or not any(r): continue
                if sum(v is not None for v in r) == 1 and r[0] and fold(r[0]).startswith("caracteristicas"):
                    save_rows(); active_section = r[0]; continue
                if len(r) >= len(cols): pending_rows.append({c: (clean(r[i]) if i < len(r) else None) for i, c in enumerate(cols)})
            save_rows()
        else:
            generic = _generic_table(current)
            if generic: tables.append(generic); warnings.append("Tabela preservada com os rótulos originais; sem mapeamento semântico canônico.")
        current = []
    def recognized_header(r: list[str | None]) -> bool:
        return bool(header_kind(r) or (len(r) >= 5 and fold(" ".join(x or "" for x in r[:5])).find("item") == 0 and any(fold(x or "").startswith(("unid", "formula")) for x in r[1:5])))
    for r in rows:
        if recognized_header(r):
            if not header_kind(r) and len(r) >= 5: r = [r[0], r[1], r[2], r[3], r[4]]
            if current and not any(recognized_header(x) for x in current): current.append(r)
            else: flush(); current = [r]
        elif current: current.append(r)
        elif sum(v is not None for v in r) == 1 and r[0] and fold(r[0]).startswith("caracteristicas"): current = [r]
    flush()
    if not tables: warnings.append("Nenhuma tabela com um cabeçalho reconhecido foi encontrada.")
    return 1, text, fields, tables, warnings
