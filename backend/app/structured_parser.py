"""Layout-aware extraction for laboratory reports.

The table detector is deliberately driven by the document's own header labels;
it has no coordinates or product/item catalogue baked into it.
"""
import io
import re
import unicodedata
from typing import Any

import pdfplumber
from .structured_geometry import parse_borderless
from .structured_generic_geometry import parse_generic_borderless
from .structured_header_alignment import aligned_rows

CANONICAL_FIELDS = ("produto", "lote", "data_le", "nota_fiscal", "data_fabricacao", "data_validade", "embalagem", "quantidade", "fornecedor", "transportadora", "cliente")
THREE = ["especificacao", "parametro", "resultado"]
# Five-column reports use a stable physical layout.  Header text is frequently
# split or mistranscribed, so these names intentionally do not come from it.
FIVE = ["item", "unidade", "especificacoes", "resultado", "observacoes"]

FIELD_ALIASES = {
    "produto": "produto", "lote": "lote", "lote int": "lote", "lote interno": "lote", "nf": "nota_fiscal",
    "notafiscal": "nota_fiscal", "n.f": "nota_fiscal", "n f": "nota_fiscal",
    "data": "data_le", "data fab": "data_fabricacao", "data de fabricacao": "data_fabricacao", "datafabricacao": "data_fabricacao",
    "data validade": "data_validade", "data de validade": "data_validade", "datavalidade": "data_validade",
    "embalagem": "embalagem", "quantidade": "quantidade", "fornecedor": "fornecedor",
    "transportadora": "transportadora", "transportador": "transportadora", "cliente": "cliente",
}

def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()
def clean(s: Any) -> str | None:
    if s is None: return None
    x = re.sub(r"\s+", " ", str(s)).strip(" \t|;")
    return x or None


def is_section_heading(value: Any) -> bool:
    normalized = fold(clean(value) or "").strip()
    return bool(re.match(r"^(?:caracteristicas|categorias?)\b", normalized))
def key(label: str) -> str | None:
    x = re.sub(r"[^a-z0-9]", "", fold(label))
    return FIELD_ALIASES.get(x) or FIELD_ALIASES.get(fold(label).strip().rstrip(".:"))


def _fold_with_map(value: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    mapping: list[int] = []
    for index, char in enumerate(value):
        folded = fold(char)
        normalized.extend(folded)
        mapping.extend([index] * len(folded))
    return "".join(normalized), mapping


def _metadata_cutoff(normalized: str) -> int | None:
    """Find a contextual table/footer boundary, avoiding single-word matches."""
    footer = re.search(r"\b(?:este\s+certificado|quimic[oa]\s+responsavel|supervis[aã]o\s+e\s+responsabilidade)\b", normalized)
    markers = list(re.finditer(r"\b(?P<marker>item|formula|unid\w*|espec\w*|observ\w*|bserv\w*|resultado|parametro)\b", normalized))
    for index, marker in enumerate(markers):
        if marker.group("marker") != "item":
            continue
        raw_families = [candidate.group("marker") for candidate in markers[index + 1 :] if candidate.start() - marker.start() <= 180]
        families = {
            "espec" if value.startswith("espec") else
            "observ" if value.startswith(("observ", "bserv")) else
            "unid" if value.startswith("unid") else value
            for value in raw_families
        }
        families.intersection_update({"formula", "unid", "espec", "observ", "resultado", "parametro"})
        if len(families) >= 2:
            boundary = marker.start()
            return min(boundary, footer.start()) if footer else boundary
    return footer.start() if footer else None

def metadata(text: str) -> dict[str, str | None]:
    out = {x: None for x in CANONICAL_FIELDS}
    # Normalize only for matching, retaining an index map so values are sliced
    # from the original text and keep accents/case exactly as supplied.
    kept: list[str] = []
    for line in text.splitlines():
        normalized = fold(line).strip()
        if re.match(r"^(?:item\s+unidade|especificacao\s+parametro\s+resultado|caracteristicas|categorias?|\[fim\])", normalized):
            break
        kept.append(line)
    pre = "\n".join(kept)
    flat_original = pre.replace("\n", " ")
    flat, mapping = _fold_with_map(flat_original)
    cutoff = _metadata_cutoff(flat)
    if cutoff is not None:
        original_cutoff = mapping[cutoff] if cutoff < len(mapping) else len(flat_original)
        flat = flat[:cutoff]
        flat_original = flat_original[:original_cutoff]
        mapping = mapping[:cutoff]
    labs = r"DATA\s+(?:DE\s+)?(?:FAB(?:RICACAO)?|VALIDADE)|DATA\s+FAB\.?|NOTA\s+FISCAL|N\.?\s*F\.?|PRODUTO|LOTE(?:\s+INT(?:ERNO)?\.?)?|EMBALAGEM|QUANTIDADE|LACRES?|FORNECEDOR|TRANSPORTADOR(?:A)?|CLIENTE|DATA"
    pat = re.compile(rf"(?i)\b(?P<label>{labs})(?=\s*:)[\s]*:")
    matches = list(pat.finditer(flat))
    for i, m in enumerate(matches):
        k = key(m.group("label"))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(flat)
        original_start = mapping[m.end()] if m.end() < len(mapping) else len(flat_original)
        original_end = mapping[end] if end < len(mapping) else len(flat_original)
        v = clean(flat_original[original_start:original_end])
        internal_lot = bool(re.match(r"(?i)lote\s+int", m.group("label")))
        if k == "lote" and internal_lot and out["lote"] is not None:
            continue
        if k: out[k] = v
    return out

def header_kind(row: list[Any]) -> str | None:
    h = [re.sub(r"[^a-z]", "", fold(clean(x) or "")) for x in row]
    if len(h) == 5 and len(set(h)) == 5 and set(h) == {"item", "unidade", "especificacoes", "resultado", "observacao"}: return "five"
    if len(h) == 5 and len(set(h)) == 5 and set(h) == {"item", "unidade", "especificacoes", "resultado", "observacoes"}: return "five"
    if len(h) == 5 and len(set(h)) == 5 and set(h) == {"item", "formulaunid", "metodoespecif", "analitico", "observacoes"}: return "five"
    if len(h) == 3 and len(set(h)) == 3 and set(h) == {"especificacao", "parametro", "resultado"}: return "three"
    return None


def _generic_columns(row: list[Any]) -> list[str]:
    columns: list[str] = []
    used: set[str] = set()
    for index, value in enumerate(row):
        base = re.sub(r"[^a-z0-9]+", "_", fold(clean(value) or "")).strip("_") or f"coluna_{index + 1}"
        label = base
        suffix = 2
        while label in used:
            label = f"{base}_{suffix}"
            suffix += 1
        used.add(label)
        columns.append(label)
    return columns


def _generic_table(rows: list[list[Any]]) -> dict[str, Any] | None:
    """Preserve an unknown 3+ column table without assigning semantics."""
    if not rows or max((len(row) for row in rows), default=0) < 3:
        return None
    normalized = [[clean(value) for value in row] for row in rows]
    first = next((row for row in normalized if sum(value is not None for value in row) >= 2), None)
    if first is None:
        return None
    first_index = normalized.index(first)
    # A mostly textual first multi-cell row is a header. If it resembles data,
    # use neutral column names and retain that row instead of dropping it.
    marker_families = set()
    for value in first:
        normalized_value = fold(value or "")
        for family, prefixes in {
            "item": ("item",), "formula": ("formula",), "metodo": ("metod",),
            "unidade": ("unid",), "espec": ("espec",), "observ": ("observ", "bserv"),
            "parametro": ("param",), "resultado": ("result",), "propriedade": ("propr",),
            "limite": ("limit",), "medido": ("medid",), "amostra": ("amostr",), "nota": ("nota",),
        }.items():
            if normalized_value.startswith(prefixes):
                marker_families.add(family)
                break
    marker_families.discard("")
    marker_cell_count = sum(1 for value in first if any(fold(value or "").startswith(prefix) for prefixes in {
        "item": ("item",), "formula": ("formula",), "metodo": ("metod",), "unidade": ("unid",),
        "espec": ("espec",), "observ": ("observ", "bserv"), "parametro": ("param",), "resultado": ("result",),
        "propriedade": ("propr",), "limite": ("limit",), "medido": ("medid",), "amostra": ("amostr",), "nota": ("nota",),
    }.values() for prefix in prefixes))
    compact_header = fold(" ".join(value or "" for value in first))
    compact_families = sum(token in compact_header for token in ("formula", "unid", "metod", "espec", "analit", "observ"))
    has_header = len(marker_families) >= 2 or compact_families >= 3 or (marker_cell_count >= 2 and marker_cell_count == sum(value is not None for value in first))
    width = max(len(row) for row in normalized)
    first = first + [None] * (width - len(first))
    columns = FIVE if width == 5 else (_generic_columns(first) if has_header else [f"coluna_{index + 1}" for index in range(width)])
    section: str | None = None
    output: list[dict[str, str | None]] = []
    header_signature = tuple(re.sub(r"[^a-z0-9]", "", fold(value or "")) for value in first)
    for index, row in enumerate(normalized):
        values = row + [None] * (len(columns) - len(row))
        values = values[: len(columns)]
        if has_header and index == first_index:
            continue
        if has_header and tuple(re.sub(r"[^a-z0-9]", "", fold(value or "")) for value in values) == header_signature:
            continue
        nonempty = [value for value in values if value is not None]
        compact = fold(" ".join(nonempty))
        if len(nonempty) == 1 and sum(token in compact for token in ("formula", "unid", "metod", "espec", "analit", "observ")) >= 3:
            continue
        if len(nonempty) == 1 and is_section_heading(nonempty[0]):
            # A section encountered after rows cannot safely be applied to
            # those rows without returning multiple tables; leave the section
            # unset rather than misattributing earlier data.
            section = nonempty[0] if not output else None
            continue
        if nonempty:
            output.append({column: values[position] for position, column in enumerate(columns)})
    if not output:
        return None
    return {"section": section, "columns": columns, "rows": output}


def _recover_clipped_items(page: Any, table: Any, rows: list[list[Any]]) -> list[list[Any]]:
    """Rebuild malformed five-cell rows from page words and cell geometry."""
    try:
        extracted = page.extract_words(keep_blank_chars=False, use_text_flow=False)
        table_rows = table.rows
        left = float(table.bbox[0])
    except (AttributeError, TypeError, ValueError):
        return rows
    if max((len(row) for row in rows), default=0) != 5:
        return rows
    # A malformed left rule may clip short words completely while longer words
    # cross it. Learn the item's x alignment from those crossing words.
    crossing_x = []
    for row in table_rows:
        cells = getattr(row, "cells", None) or []
        if len(cells) != 5 or cells[0] is None:
            continue
        bound = float(cells[0][0])
        rb = row.bbox
        for word in extracted:
            middle = (float(word["top"]) + float(word["bottom"])) / 2
            if float(rb[1]) <= middle <= float(rb[3]) and float(word["x0"]) < bound < float(word["x1"]):
                crossing_x.append(float(word["x0"]))
    if not crossing_x:
        for row in table_rows:
            rb = row.bbox; cells = getattr(row, "cells", None) or []
            if not cells or cells[0] is None: continue
            bound = float(cells[0][0])
            crossing_x.extend(float(word["x0"]) for word in extracted
                if float(rb[1]) <= (float(word["top"])+float(word["bottom"])) / 2 <= float(rb[3]) and float(word["x1"]) <= bound)
    anchor_x = sorted(crossing_x)[len(crossing_x) // 2] if crossing_x else None
    for index, values in enumerate(rows):
        if index >= len(table_rows):
            continue
        row = table_rows[index]; bbox = row.bbox
        cells = getattr(row, "cells", None) or []
        if len(cells) != 5 or any(cell is None or len(cell) < 4 for cell in cells):
            continue
        words = [word for word in extracted if float(bbox[1]) <= (float(word["top"]) + float(word["bottom"])) / 2 <= float(bbox[3])]
        rebuilt = [[] for _ in range(5)]
        for word in words:
            center = (float(word["x0"]) + float(word["x1"])) / 2
            target = next((pos for pos, cell in enumerate(cells) if cell is not None and float(cell[0]) <= center <= float(cell[2])), None)
            if target is None and cells[0] is not None and float(word["x0"]) < float(cells[0][0]) < float(word["x1"]):
                target = 0
            if target is None and cells[0] is not None and anchor_x is not None and abs(float(word["x0"]) - anchor_x) <= 8 and float(word["x1"]) <= float(cells[0][0]):
                target = 0
            if target is not None:
                rebuilt[target].append(str(word.get("text", "")))
        if any(rebuilt):
            values[:] = [" ".join(part) or None for part in rebuilt]
    return rows


def parse(raw: bytes) -> tuple[int, str, dict[str, str | None], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []; pages_text: list[str] = []; metadata_pages: list[str] = []; tables: list[dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""; pages_text.append(text)
            found = page.find_tables()
            page_metadata_text = text
            if found:
                try:
                    data_tables = []
                    for candidate in found:
                        candidate_rows = candidate.extract()
                        if any(header_kind(row) for row in candidate_rows) or max((len(row) for row in candidate_rows), default=0) >= 3:
                            data_tables.append(candidate)
                    first_bbox = min((table.bbox[1] for table in data_tables), default=None)
                    if first_bbox is not None:
                        page_metadata_text = page.crop((0, 0, page.width, first_bbox)).extract_text() or ""
                except (AttributeError, TypeError, ValueError):
                    page_metadata_text = text
            metadata_pages.append(page_metadata_text)
            recognized = False
            for table in found:
                rows = table.extract()
                aligned = aligned_rows(page, table, rows)
                if aligned is not None:
                    rows = aligned
                else:
                    rows = _recover_clipped_items(page, table, rows)
                kind = next((k for r in rows if r and (k := header_kind(r))), None)
                if not kind:
                    generic = _generic_table(rows)
                    if generic:
                        tables.append(generic)
                        warnings.append("Tabela preservada com os rótulos originais; sem mapeamento semântico canônico.")
                        recognized = True
                    continue
                recognized = True
                cols = THREE if kind == "three" else FIVE
                header_values = next([clean(x) for x in r] for r in rows if r and header_kind(r) == kind)
                # Five-cell tables are mapped strictly by physical position;
                # malformed labels must never rename or reorder the contract.
                aliases = {"especificacao": "especificacao", "especificacoes": "especificacoes", "parametro": "parametro", "resultado": "resultado", "item": "item", "unidade": "unidade", "observacao": "observacao"}
                physical_cols = list(range(len(cols))) if kind == "five" else [aliases.get(re.sub(r"[^a-z]", "", fold(x or "")), cols[i] if i < len(cols) else "") for i, x in enumerate(header_values)]
                current: str | None = None
                for before in rows:
                    vals0 = [clean(x) for x in before]
                    if header_kind(vals0) == kind: break
                    if len([x for x in vals0 if x]) == 1 and vals0[0] and is_section_heading(vals0[0]):
                        current = vals0[0]
                data_rows: list[dict[str, str | None]] = []
                seen_header = False
                for row in rows:
                    vals = [clean(x) for x in row]
                    if header_kind(vals) == kind: seen_header = True; continue
                    if not seen_header: continue
                    nonempty = [x for x in vals if x]
                    if len(nonempty) == 1 and is_section_heading(nonempty[0]):
                        new_section = nonempty[0]
                        if data_rows:
                            tables.append({"section": current, "columns": cols, "rows": data_rows}); data_rows = []
                        current = new_section; continue
                    if not nonempty or len(vals) < len(cols): continue
                    data_rows.append({c: (vals[i] if i < len(vals) else None) for i, c in enumerate(cols)} if kind == "five" else {c: (vals[physical_cols.index(c)] if c in physical_cols and physical_cols.index(c) < len(vals) else None) for c in cols})
                if data_rows: tables.append({"section": current, "columns": cols, "rows": data_rows})
            if not recognized:
                # Borderless fallback: header word x positions define column bands.
                geo_tables, geo_warnings, geo_header_top = parse_borderless(page)
                if geo_tables:
                    for gt in geo_tables:
                        hint = re.search(r"(?im)^\s*(CARACTERISTICAS[^\n]+)", text)
                        if gt.get("section") is None and hint: gt["section"] = clean(hint.group(1))
                    tables.extend(geo_tables)
                warnings.extend(geo_warnings)
                if geo_tables:
                    if geo_header_top is not None:
                        try:
                            metadata_pages[-1] = page.crop((0, 0, page.width, max(0, geo_header_top - 1))).extract_text() or ""
                        except (AttributeError, TypeError, ValueError):
                            pass
                    continue
                generic_tables, generic_warnings, generic_header_top = parse_generic_borderless(page)
                if generic_tables:
                    if generic_header_top is not None:
                        try:
                            metadata_pages[-1] = page.crop((0, 0, page.width, max(0, generic_header_top - 1))).extract_text() or ""
                        except (AttributeError, TypeError, ValueError):
                            pass
                    tables.extend(generic_tables)
                    warnings.extend(generic_warnings)
                    recognized = True
                else:
                    warnings.extend(generic_warnings)
            if found and not recognized:
                warnings.append("Tabela encontrada sem cabeçalho canônico; linhas não foram inferidas automaticamente.")
        text = "\n\n".join(pages_text).strip()
    metadata_text = "\n\n".join(metadata_pages).strip()
    if not tables:
        if re.search(r"(?i)ESPECIFICA(?:ÇÃO|CAO)\s+PARAMETRO\s+RESULTADO", text):
            warnings.append("Cabeçalho achatado sem separação suficiente; linhas ambíguas não foram inferidas.")
        else:
            warnings.append("Nenhuma tabela com um cabeçalho reconhecido foi encontrada.")
    return len(pages_text), text, metadata(metadata_text), tables, warnings
