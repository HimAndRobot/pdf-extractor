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

CANONICAL_FIELDS = ("produto", "lote", "data", "nota_fiscal", "data_fabricacao", "data_validade", "embalagem", "quantidade", "fornecedor", "transportadora", "cliente")
THREE = ["especificacao", "parametro", "resultado"]
FIVE = ["item", "unidade", "especificacoes", "resultado", "observacao"]

FIELD_ALIASES = {
    "produto": "produto", "lote": "lote", "data": "data", "nf": "nota_fiscal",
    "notafiscal": "nota_fiscal", "n.f": "nota_fiscal", "n f": "nota_fiscal",
    "data fab": "data_fabricacao", "data de fabricacao": "data_fabricacao", "datafabricacao": "data_fabricacao",
    "data validade": "data_validade", "data de validade": "data_validade", "datavalidade": "data_validade",
    "embalagem": "embalagem", "quantidade": "quantidade", "fornecedor": "fornecedor",
    "transportadora": "transportadora", "cliente": "cliente",
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
    labs = r"DATA\s+(?:DE\s+)?(?:FAB(?:RICACAO)?|VALIDADE)|DATA\s+FAB\.?|NOTA\s+FISCAL|N\.?\s*F\.?|PRODUTO|LOTE|EMBALAGEM|QUANTIDADE|FORNECEDOR|TRANSPORTADORA|CLIENTE|DATA"
    pat = re.compile(rf"(?i)\b(?P<label>{labs})(?=\s*:)[\s]*:")
    matches = list(pat.finditer(flat))
    for i, m in enumerate(matches):
        k = key(m.group("label"))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(flat)
        original_start = mapping[m.end()] if m.end() < len(mapping) else len(flat_original)
        original_end = mapping[end] if end < len(mapping) else len(flat_original)
        v = clean(flat_original[original_start:original_end])
        if k: out[k] = v
    return out

def header_kind(row: list[Any]) -> str | None:
    h = [re.sub(r"[^a-z]", "", fold(clean(x) or "")) for x in row]
    if len(h) >= 5 and {"item", "unidade", "resultado"}.issubset(h): return "five"
    if len(h) >= 3 and {"especificacao", "parametro", "resultado"}.issubset(h): return "three"
    return None

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
                rows = table.extract(); kind = next((k for r in rows if r and (k := header_kind(r))), None)
                if not kind: continue
                recognized = True
                cols = THREE if kind == "three" else FIVE
                header_values = next([clean(x) for x in r] for r in rows if r and header_kind(r) == kind)
                aliases = {"especificacao": "especificacao", "especificacoes": "especificacoes", "parametro": "parametro", "resultado": "resultado", "item": "item", "unidade": "unidade", "observacao": "observacao"}
                physical_cols = [aliases.get(re.sub(r"[^a-z]", "", fold(x or "")), cols[i] if i < len(cols) else "") for i, x in enumerate(header_values)]
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
                    data_rows.append({c: (vals[physical_cols.index(c)] if c in physical_cols and physical_cols.index(c) < len(vals) else None) for c in cols})
                if data_rows: tables.append({"section": current, "columns": cols, "rows": data_rows})
            if not recognized:
                # Borderless fallback: header word x positions define column bands.
                geo_tables, geo_warnings, _ = parse_borderless(page)
                if geo_tables:
                    for gt in geo_tables:
                        hint = re.search(r"(?im)^\s*(CARACTERISTICAS[^\n]+)", text)
                        if gt.get("section") is None and hint: gt["section"] = clean(hint.group(1))
                    tables.extend(geo_tables)
                warnings.extend(geo_warnings)
                if geo_tables:
                    continue
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
