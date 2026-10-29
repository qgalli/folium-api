import csv
import io
import json
import random
import re
import zipfile
import xml.etree.ElementTree as ET
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.utils import timezone
from .models import Book, Item, Author, Genre, Editorial, User


class IsLibrarianOrAdminUser(permissions.BasePermission):
    """
    Permiso que restringe el uso del importador exclusivamente
    a usuarios con rol LIBRARIAN o ADMIN.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return (
            getattr(request.user, "rol", None) in [User.Rol.LIBRARIAN, User.Rol.ADMIN]
            or request.user.is_staff
            or request.user.is_superuser
        )


def _clean_str(val):
    if val is None:
        return ""
    return str(val).strip()


def _sanitize_name_text(text, max_len=45, default="Autor"):
    cleaned = _clean_str(text)
    # Permite letras, espacios, apóstrofes y guiones según regla Author.clean()
    cleaned = re.sub(r"[^a-zA-ZÀ-ÿ\s'-]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = default
    return cleaned[:max_len]


def _clean_isbn(isbn_val):
    digits = re.sub(r"[^0-9X]", "", _clean_str(isbn_val).upper())
    if len(digits) in (10, 13):
        return digits
    return None


def parse_importer_options(options_raw):
    default_opts = {
        "genre_separator": "auto",
        "author_format": "auto",
        "seen_isbns": [],
        "seen_titles": [],
    }
    if not options_raw:
        return default_opts
    try:
        parsed = json.loads(options_raw) if isinstance(options_raw, str) else options_raw
        if isinstance(parsed, dict):
            return {
                "genre_separator": parsed.get("genre_separator") or "auto",
                "author_format": parsed.get("author_format") or "auto",
                "seen_isbns": parsed.get("seen_isbns") if isinstance(parsed.get("seen_isbns"), list) else [],
                "seen_titles": parsed.get("seen_titles") if isinstance(parsed.get("seen_titles"), list) else [],
            }
    except Exception:
        pass
    return default_opts


def split_and_clean_genres(raw_genre, separator_mode="auto"):
    """
    Separa cadenas con múltiples géneros (ej. "Ficción, Misterio, Clásicos")
    en nombres individuales limpios, sin duplicados y truncados a 100 caracteres.
    """
    cleaned_raw = _clean_str(raw_genre)
    if not cleaned_raw:
        return ["General"]

    if separator_mode == "none":
        tokens = [cleaned_raw]
    elif separator_mode == "comma":
        tokens = re.split(r",+", cleaned_raw)
    elif separator_mode == "semicolon":
        tokens = re.split(r";+", cleaned_raw)
    elif separator_mode == "slash":
        tokens = re.split(r"/+", cleaned_raw)
    else:
        # Modo automático: divide por coma, punto y coma, barra o tubería
        tokens = re.split(r"[,;/|]+", cleaned_raw)

    result = []
    seen_lower = set()
    for token in tokens:
        g = re.sub(r"^[\s.,;:/\-–—]+|[\s.,;:/\-–—]+$", "", _clean_str(token))
        g = re.sub(r"\s+", " ", g).strip()[:100]
        if g and g.lower() not in seen_lower:
            seen_lower.add(g.lower())
            result.append(g)

    return result if result else ["General"]


def _split_fullname_into_pair(fullname_str):
    parts = fullname_str.split()
    if len(parts) >= 2:
        first_name = _sanitize_name_text(parts[0], 45, "Autor")
        last_name = _sanitize_name_text(" ".join(parts[1:]), 45, "-")
    else:
        first_name = _sanitize_name_text(fullname_str, 45, "Autor")
        last_name = "-"
    return (first_name, last_name)


def split_and_clean_authors(raw_author, author_format="auto"):
    """
    Analiza la celda de autor(es) y devuelve una lista de tuplas (first_name, last_name).
    En modo 'auto' distingue entre un autor escrito como "Apellido, Nombre"
    (ej. "Borges, Jorge Luis" o "García Márquez, Gabriel") y múltiples autores
    separados por coma, punto y coma o conjunciones.
    """
    cleaned_raw = _clean_str(raw_author)
    if not cleaned_raw or cleaned_raw.lower() == "autor no especificado":
        return [("Autor", "-")]

    pairs = []

    if author_format == "lastname_firstname":
        # Varios autores se separan por ';' o 'and'/'&'; la coma interna invierte "Apellido, Nombre"
        raw_authors = [a.strip() for a in re.split(r";+|\s+(?:and|&)\s+", cleaned_raw, flags=re.IGNORECASE) if a.strip()]
        for item in raw_authors:
            if "," in item:
                last_part, first_part = item.split(",", 1)
                fn = _sanitize_name_text(first_part, 45, "Autor")
                ln = _sanitize_name_text(last_part, 45, "-")
                pairs.append((fn, ln))
            else:
                pairs.append(_split_fullname_into_pair(item))

    elif author_format == "firstname_lastname":
        # Cada coma o punto y coma separa autores distintos en orden "Nombre Apellido"
        raw_authors = [
            a.strip()
            for a in re.split(r"[,;]+|\s+(?:and|y|&)\s+", cleaned_raw, flags=re.IGNORECASE)
            if a.strip()
        ]
        for item in raw_authors:
            pairs.append(_split_fullname_into_pair(item))

    else:
        # Modo automático ("auto")
        if ";" in cleaned_raw or re.search(r"\s+(?:and|&)\s+", cleaned_raw, flags=re.IGNORECASE):
            segments = [
                s.strip()
                for s in re.split(r";+|\s+(?:and|&)\s+", cleaned_raw, flags=re.IGNORECASE)
                if s.strip()
            ]
            for seg in segments:
                if seg.count(",") == 1:
                    last_part, first_part = seg.split(",", 1)
                    fn = _sanitize_name_text(first_part, 45, "Autor")
                    ln = _sanitize_name_text(last_part, 45, "-")
                    pairs.append((fn, ln))
                else:
                    for sub in [x.strip() for x in seg.split(",") if x.strip()]:
                        pairs.append(_split_fullname_into_pair(sub))
        elif "," in cleaned_raw:
            comma_parts = [p.strip() for p in cleaned_raw.split(",") if p.strip()]
            if len(comma_parts) == 2:
                w0 = len(comma_parts[0].split())
                w1 = len(comma_parts[1].split())
                # Heurística para "Apellido, Nombre" (ej. "Borges, Jorge Luis" [1,2] o "García Márquez, Gabriel" [2,1])
                if (w0 == 1 and w1 <= 3) or (w0 <= 2 and w1 == 1):
                    fn = _sanitize_name_text(comma_parts[1], 45, "Autor")
                    ln = _sanitize_name_text(comma_parts[0], 45, "-")
                    pairs.append((fn, ln))
                else:
                    for part in comma_parts:
                        pairs.append(_split_fullname_into_pair(part))
            else:
                for part in comma_parts:
                    pairs.append(_split_fullname_into_pair(part))
        else:
            # Sin comas ni punto y coma; verificar si hay " y " entre dos nombres completos
            y_parts = [p.strip() for p in re.split(r"\s+y\s+", cleaned_raw, flags=re.IGNORECASE) if p.strip()]
            if len(y_parts) > 1 and all(len(p.split()) >= 2 for p in y_parts):
                for part in y_parts:
                    pairs.append(_split_fullname_into_pair(part))
            else:
                pairs.append(_split_fullname_into_pair(cleaned_raw))

    # Desduplicar preservando orden y limitar a los primeros 5 autores
    unique_pairs = []
    seen = set()
    for fn, ln in pairs:
        key = (fn.lower(), ln.lower())
        if key not in seen:
            seen.add(key)
            unique_pairs.append((fn, ln))

    return unique_pairs[:5] if unique_pairs else [("Autor", "-")]


def _excel_col_to_index(cell_ref):
    if not cell_ref:
        return None
    col_letters = "".join(ch for ch in str(cell_ref) if ch.isalpha()).upper()
    if not col_letters:
        return None
    idx = 0
    for ch in col_letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def parse_csv_file(file_bytes):
    # Detección de encoding
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            text = file_bytes.decode(enc)
            break
        except (UnicodeDecodeError, AttributeError):
            continue
    else:
        text = file_bytes.decode("utf-8", errors="replace")

    # Detección de delimitador
    sample = text[:4096]
    delimiter = ","
    if ";" in sample and sample.count(";") > sample.count(","):
        delimiter = ";"
    elif "\t" in sample and sample.count("\t") > sample.count(","):
        delimiter = "\t"

    stream = io.StringIO(text)
    reader = csv.DictReader(stream, delimiter=delimiter)
    headers = [h.strip() for h in (reader.fieldnames or []) if h]
    rows = []
    for r in reader:
        cleaned_row = {k.strip(): _clean_str(v) for k, v in r.items() if k}
        if any(cleaned_row.values()):
            rows.append(cleaned_row)

    return headers, rows


def parse_xlsx_file(file_bytes):
    # Parser nativo de XLSX usando zipfile y ElementTree estándar con alineación por coordenada de celda
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_tree.findall(f"{ns}si"):
                shared_strings.append("".join(si.itertext()))

        sheet_xml = zf.read("xl/worksheets/sheet1.xml")
        sheet_tree = ET.fromstring(sheet_xml)

        matrix = []
        for row in sheet_tree.iter(f"{ns}row"):
            row_cells = {}
            next_col_idx = 0
            for c in row.iter(f"{ns}c"):
                col_idx = _excel_col_to_index(c.get("r"))
                if col_idx is None:
                    col_idx = next_col_idx
                next_col_idx = col_idx + 1

                cell_type = c.get("t")
                cell_val = ""
                if cell_type == "inlineStr":
                    is_el = c.find(f"{ns}is")
                    cell_val = "".join(is_el.itertext()) if is_el is not None else ""
                else:
                    v_el = c.find(f"{ns}v")
                    if v_el is not None and v_el.text is not None:
                        raw_val = v_el.text
                        if cell_type == "s":
                            idx = int(raw_val)
                            cell_val = shared_strings[idx] if idx < len(shared_strings) else ""
                        else:
                            cell_val = raw_val

                row_cells[col_idx] = cell_val

            if row_cells and any(_clean_str(v) for v in row_cells.values()):
                max_col = max(row_cells.keys())
                row_vals = [row_cells.get(i, "") for i in range(max_col + 1)]
                matrix.append(row_vals)

        if not matrix:
            return [], []

        headers = [_clean_str(h) for h in matrix[0]]
        rows = []
        for r in matrix[1:]:
            row_dict = {}
            for idx, h in enumerate(headers):
                if h:
                    row_dict[h] = _clean_str(r[idx]) if idx < len(r) else ""
            if any(row_dict.values()):
                rows.append(row_dict)

        return headers, rows
    except Exception as e:
        raise ValueError(f"No se pudo procesar el archivo Excel: {str(e)}")


def clean_bibtex_value(val):
    if not val:
        return ""
    val = str(val).strip()
    if (val.startswith("{") and val.endswith("}")) or (val.startswith('"') and val.endswith('"')):
        val = val[1:-1].strip()

    # Normalizar dotless i de LaTeX
    val = val.replace(r"{\i}", "i").replace(r"\i", "i")

    # Reemplazo de acentos y caracteres especiales comunes en BibTeX / LaTeX
    accents = {
        "'": {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú"},
        "`": {"a": "à", "e": "è", "i": "ì", "o": "ò", "u": "ù", "A": "À", "E": "È", "I": "Ì", "O": "Ò", "U": "Ù"},
        "^": {"a": "â", "e": "ê", "i": "î", "o": "ô", "u": "û", "A": "Â", "E": "Ê", "I": "Î", "O": "Ô", "U": "Û"},
        '"': {"a": "ä", "e": "ë", "i": "ï", "o": "ö", "u": "ü", "A": "Ä", "E": "Ë", "I": "Ï", "O": "Ö", "U": "Ü"},
        "~": {"a": "ã", "n": "ñ", "o": "õ", "A": "Ã", "N": "Ñ", "O": "Õ"},
        "c": {"c": "ç", "C": "Ç"},
    }
    for acc, mapping in accents.items():
        for char, repl in mapping.items():
            val = val.replace("{\\" + acc + "{" + char + "}}", repl)
            val = val.replace("{\\" + acc + char + "}", repl)
            val = val.replace("\\" + acc + "{" + char + "}", repl)
            val = val.replace("\\" + acc + char, repl)

    # Remover llaves restantes usadas para proteger mayúsculas (ej. {LaTeX} o {NASA})
    while "{" in val and "}" in val:
        new_val = re.sub(r"\{([^{}]*)\}", r"\1", val)
        if new_val == val:
            break
        val = new_val
    val = val.replace("{", "").replace("}", "")
    val = val.replace("--", "-").replace("---", "—")
    val = re.sub(r"\s+", " ", val).strip()
    return val


def format_bibtex_authors(author_str):
    if not author_str:
        return ""
    # En BibTeX los autores múltiples vienen separados por ' and '
    authors = re.split(r"\s+and\s+", str(author_str), flags=re.IGNORECASE)
    formatted = []
    for a in authors:
        a = clean_bibtex_value(a)
        if not a:
            continue
        if "," in a:
            # Formato "Apellido, Nombre" -> "Nombre Apellido"
            parts = a.split(",", 1)
            formatted.append(f"{parts[1].strip()} {parts[0].strip()}".strip())
        else:
            formatted.append(a)
    return ", ".join(formatted)


def parse_bib_file(file_bytes):
    """
    Parser nativo de archivos BibTeX (.bib) utilizando la biblioteca estándar de Python.
    Extrae cada entrada (@book, @article, etc.) como una fila con sus atributos normalizados.
    """
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            text = file_bytes.decode(enc)
            break
        except (UnicodeDecodeError, AttributeError):
            continue
    else:
        text = file_bytes.decode("utf-8", errors="replace")

    # Expresión para identificar el inicio de cada entrada @tipo{clave,
    entry_pattern = re.compile(r"@([a-zA-Z]+)\s*\{\s*([^,\s\}]+)\s*,", re.UNICODE)

    rows = []
    headers_set = set(["title", "author"])
    pos = 0

    while True:
        match = entry_pattern.search(text, pos)
        if not match:
            break

        entry_type = match.group(1).lower()
        citation_key = match.group(2).strip()

        # Omitir entradas que no representen documentos (comentarios, macros, preámbulos)
        if entry_type in ("comment", "string", "preamble"):
            pos = match.end()
            continue

        entry_start = match.end()
        brace_depth = 1
        i = entry_start
        in_quotes = False
        entry_body = ""

        # Encontrar el delimitador de cierre respetando anidación de llaves y comillas
        while i < len(text) and brace_depth > 0:
            ch = text[i]
            if ch == '"' and text[i - 1:i] != "\\":
                in_quotes = not in_quotes
            elif not in_quotes:
                if ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        entry_body = text[entry_start:i]
                        break
            i += 1

        pos = i + 1

        row = {
            "entry_type": entry_type,
            "citation_key": citation_key,
        }
        headers_set.add("entry_type")
        headers_set.add("citation_key")

        # Parsear los campos clave = valor dentro del cuerpo de la entrada
        body_idx = 0
        while body_idx < len(entry_body):
            eq_idx = entry_body.find("=", body_idx)
            if eq_idx == -1:
                break

            field_name = entry_body[body_idx:eq_idx].strip()
            field_name = field_name.lstrip(", \t\r\n").strip().lower()

            val_start = eq_idx + 1
            while val_start < len(entry_body) and entry_body[val_start] in " \t\r\n":
                val_start += 1

            if val_start >= len(entry_body):
                break

            val_first_char = entry_body[val_start]
            val_end = val_start

            if val_first_char == "{":
                depth = 0
                for vi in range(val_start, len(entry_body)):
                    if entry_body[vi] == "{":
                        depth += 1
                    elif entry_body[vi] == "}":
                        depth -= 1
                        if depth == 0:
                            val_end = vi + 1
                            break
                raw_val = entry_body[val_start:val_end]
                body_idx = val_end
            elif val_first_char == '"':
                vi = val_start + 1
                while vi < len(entry_body):
                    if entry_body[vi] == '"' and entry_body[vi - 1:vi] != "\\":
                        val_end = vi + 1
                        break
                    vi += 1
                raw_val = entry_body[val_start:val_end]
                body_idx = val_end
            else:
                # Valor no delimitado (ej. números en 'year = 1999,')
                comma_idx = entry_body.find(",", val_start)
                if comma_idx == -1:
                    raw_val = entry_body[val_start:].strip()
                    body_idx = len(entry_body)
                else:
                    raw_val = entry_body[val_start:comma_idx].strip()
                    body_idx = comma_idx + 1

            if field_name:
                cleaned_field = clean_bibtex_value(raw_val)
                if field_name == "author":
                    cleaned_field = format_bibtex_authors(raw_val)
                row[field_name] = cleaned_field
                headers_set.add(field_name)

        if row.get("title") or row.get("author"):
            rows.append(row)

    # Ordenar cabeceras priorizando las columnas principales para el catálogo
    priority_headers = ["title", "author", "isbn", "publisher", "year", "keywords", "abstract", "entry_type", "citation_key"]
    sorted_headers = [h for h in priority_headers if h in headers_set]
    sorted_headers += sorted([h for h in headers_set if h not in priority_headers])

    return sorted_headers, rows


def clean_marc_punct(text):
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r"[\s/;:,.=\]]+$", "", text).strip()
    text = re.sub(r"^[\s\[]+", "", text).strip()
    return text


def format_marc_author(name_str):
    if not name_str:
        return ""
    name_str = clean_marc_punct(name_str)
    # Remover fechas de nacimiento/defunción comunes en MARC (ej. '1927-2014' o '1899-')
    name_str = re.sub(r",\s*\d{4}\s*-\s*\d{0,4}\.?$", "", name_str).strip()
    name_str = clean_marc_punct(name_str)
    if "," in name_str:
        parts = [p.strip() for p in name_str.split(",", 1)]
        if len(parts) == 2 and parts[1]:
            return f"{parts[1]} {parts[0]}".strip()
    return name_str


def extract_marc_year(date_str):
    if not date_str:
        return ""
    match = re.search(r"\b(1[4-9]\d{2}|20\d{2})\b", str(date_str))
    return match.group(1) if match else ""


def clean_marc_isbn(val):
    if not val:
        return ""
    clean = re.sub(r"[^0-9X]", "", str(val).upper())
    if len(clean) in (10, 13):
        return clean
    # Si contiene texto adicional (ej. "9780307474728 (pbk.)"), extraer la secuencia de ISBN
    m = re.search(r"\b(97[89][0-9]{10}|[0-9]{9}[0-9X])\b", str(val).upper())
    if m:
        return m.group(1)
    return clean[:13] if clean else ""


def parse_marc_record_fields(fields, control_fields, leader=""):
    """
    Normaliza los campos catalográficos de un registro MARC 21 / MARCXML
    al esquema de Folium (título, autor, ISBN, editorial, año, género, signatura, etc.).
    """
    row = {}

    # 1. Título de la obra (245 $a, $b)
    title_parts = []
    for tag, subfields in fields:
        if tag == "245":
            sub_map = dict(subfields)
            a = clean_marc_punct(sub_map.get("a", ""))
            b = clean_marc_punct(sub_map.get("b", ""))
            if a and b:
                title_parts.append(f"{a} : {b}")
            elif a:
                title_parts.append(a)
            break
    if not title_parts:
        for tag, subfields in fields:
            if tag in ("240", "246"):
                sub_map = dict(subfields)
                a = clean_marc_punct(sub_map.get("a", ""))
                if a:
                    title_parts.append(a)
                    break
    row["title"] = title_parts[0] if title_parts else ""

    # 2. Autor(es) (100 $a, 700 $a, 110 $a)
    authors = []
    for tag, subfields in fields:
        if tag == "100":
            sub_map = dict(subfields)
            a = sub_map.get("a", "")
            if a:
                authors.append(format_marc_author(a))
    for tag, subfields in fields:
        if tag == "700":
            sub_map = dict(subfields)
            a = sub_map.get("a", "")
            if a:
                formatted = format_marc_author(a)
                if formatted not in authors:
                    authors.append(formatted)
    if not authors:
        for tag, subfields in fields:
            if tag in ("110", "710"):
                sub_map = dict(subfields)
                a = clean_marc_punct(sub_map.get("a", ""))
                if a and a not in authors:
                    authors.append(a)
    row["author"] = ", ".join(authors) if authors else ""

    # 3. ISBN (020 $a, $z)
    isbn = ""
    for tag, subfields in fields:
        if tag == "020":
            sub_map = dict(subfields)
            val = sub_map.get("a", "") or sub_map.get("z", "")
            cleaned = clean_marc_isbn(val)
            if cleaned:
                isbn = cleaned
                break
    row["isbn"] = isbn

    # 4. Editorial (264 $b o 260 $b)
    editorial = ""
    for tag, subfields in fields:
        if tag == "264":
            sub_map = dict(subfields)
            b = clean_marc_punct(sub_map.get("b", ""))
            if b:
                editorial = b
                break
    if not editorial:
        for tag, subfields in fields:
            if tag == "260":
                sub_map = dict(subfields)
                b = clean_marc_punct(sub_map.get("b", ""))
                if b:
                    editorial = b
                    break
    row["editorial"] = editorial

    # 5. Año de publicación (264 $c, 260 $c o campo fijo 008)
    year = ""
    for tag, subfields in fields:
        if tag in ("264", "260"):
            sub_map = dict(subfields)
            c = sub_map.get("c", "")
            y = extract_marc_year(c)
            if y:
                year = y
                break
    if not year and "008" in control_fields:
        f008 = control_fields["008"]
        if len(f008) >= 11:
            y = extract_marc_year(f008[7:11])
            if y:
                year = y
    row["year"] = year

    # 6. Género / Materias (650 $a, 655 $a, 651 $a)
    genres = []
    for tag, subfields in fields:
        if tag in ("650", "655", "651"):
            sub_map = dict(subfields)
            a = clean_marc_punct(sub_map.get("a", ""))
            if a and a not in genres:
                genres.append(a)
    row["genre"] = ", ".join(genres[:3]) if genres else ""

    # 7. Sinopsis / Descripción (520 $a, 500 $a)
    desc = ""
    for tag, subfields in fields:
        if tag == "520":
            sub_map = dict(subfields)
            a = clean_marc_punct(sub_map.get("a", ""))
            if a:
                desc = a
                break
    if not desc:
        for tag, subfields in fields:
            if tag == "500":
                sub_map = dict(subfields)
                a = clean_marc_punct(sub_map.get("a", ""))
                if a:
                    desc = a
                    break
    row["description"] = desc

    # 8. Signatura / Código de inventario (852 $p, 952 $p, 082 $a, 001)
    inv = ""
    for tag, subfields in fields:
        if tag in ("852", "952", "949"):
            sub_map = dict(subfields)
            p = clean_marc_punct(sub_map.get("p", ""))
            if p:
                inv = p
                break
    if not inv:
        for tag, subfields in fields:
            if tag in ("082", "090"):
                sub_map = dict(subfields)
                a = clean_marc_punct(sub_map.get("a", ""))
                if a:
                    inv = a
                    break
    if not inv and "001" in control_fields:
        inv = clean_marc_punct(control_fields["001"])
    row["inventory_code"] = inv

    # 9. Ubicación en sala (852 $c, $h o 952 $c)
    loc = ""
    for tag, subfields in fields:
        if tag in ("852", "952"):
            sub_map = dict(subfields)
            c = clean_marc_punct(sub_map.get("c", ""))
            h = clean_marc_punct(sub_map.get("h", ""))
            loc = f"{c} - {h}".strip(" -") if c and h else (c or h)
            if loc:
                break
    row["location"] = loc

    return row


def parse_marc21_bytes(file_bytes):
    """
    Parser nativo de registros MARC 21 en formato de comunicación ISO 2709 (.mrc, .marc, .dat).
    Decodifica líder, directorio de etiquetas y campos variables con soporte multirregistro y UTF-8.
    """
    rows = []
    headers_set = set(["title", "author"])
    pos = 0
    total = len(file_bytes)

    while pos < total:
        if pos + 24 > total:
            break
        try:
            rec_len = int(file_bytes[pos:pos+5].decode("ascii", errors="ignore"))
        except ValueError:
            next_rt = file_bytes.find(b"\x1d", pos)
            if next_rt != -1:
                pos = next_rt + 1
                continue
            break

        if rec_len < 25 or pos + rec_len > total:
            next_rt = file_bytes.find(b"\x1d", pos)
            if next_rt != -1:
                rec_len = next_rt - pos + 1
            else:
                break

        rec_bytes = file_bytes[pos:pos+rec_len]
        pos += rec_len

        leader = rec_bytes[:24]
        is_utf8 = leader[9:10] == b"a"
        enc = "utf-8" if is_utf8 else "latin-1"

        try:
            base_address = int(leader[12:17].decode("ascii", errors="ignore"))
        except ValueError:
            continue

        dir_bytes = rec_bytes[24:base_address]
        body_bytes = rec_bytes[base_address:]

        fields = []
        control_fields = {}

        for i in range(0, len(dir_bytes) - 1, 12):
            entry = dir_bytes[i:i+12]
            if len(entry) < 12:
                break
            tag = entry[:3].decode("ascii", errors="ignore")
            try:
                f_len = int(entry[3:7].decode("ascii", errors="ignore"))
                f_start = int(entry[7:12].decode("ascii", errors="ignore"))
            except ValueError:
                continue

            f_raw = body_bytes[f_start:f_start+f_len].rstrip(b"\x1e\x1d")

            try:
                f_tag_num = int(tag)
            except ValueError:
                f_tag_num = 999

            if f_tag_num < 10:
                control_fields[tag] = f_raw.decode(enc, errors="replace").strip()
            else:
                sub_parts = f_raw[2:].split(b"\x1f") if len(f_raw) >= 2 else []
                subfields = []
                for p in sub_parts:
                    if p:
                        code = p[:1].decode("ascii", errors="ignore")
                        val = p[1:].decode(enc, errors="replace").strip()
                        subfields.append((code, val))
                fields.append((tag, subfields))

        row = parse_marc_record_fields(fields, control_fields, leader.decode("ascii", errors="ignore"))
        if row.get("title") or row.get("author"):
            rows.append(row)
            for k in row.keys():
                if row[k]:
                    headers_set.add(k)

    priority_headers = ["title", "author", "isbn", "editorial", "year", "genre", "description", "inventory_code", "location"]
    sorted_headers = [h for h in priority_headers if h in headers_set]
    sorted_headers += sorted([h for h in headers_set if h not in priority_headers])
    return sorted_headers, rows


def parse_marcxml_bytes(file_bytes):
    """
    Parser nativo de registros bibliográficos MARCXML (.xml, .marcxml) según el esquema
    oficial de la Library of Congress (LOC MARC 21 XML Schema).
    """
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
        try:
            text = file_bytes.decode(enc)
            break
        except (UnicodeDecodeError, AttributeError):
            continue
    else:
        text = file_bytes.decode("utf-8", errors="replace")

    try:
        root = ET.fromstring(text)
    except Exception as e:
        raise ValueError(f"No se pudo interpretar el archivo MARCXML: {str(e)}")

    rows = []
    headers_set = set(["title", "author"])

    for elem in root.iter():
        tag_name = elem.tag.split("}")[-1].lower()
        if tag_name == "record":
            fields = []
            control_fields = {}
            leader = ""
            for child in elem:
                c_tag = child.tag.split("}")[-1].lower()
                if c_tag == "leader":
                    leader = child.text or ""
                elif c_tag == "controlfield":
                    ftag = child.attrib.get("tag", "")
                    control_fields[ftag] = (child.text or "").strip()
                elif c_tag == "datafield":
                    ftag = child.attrib.get("tag", "")
                    subfields = []
                    for sub in child:
                        if sub.tag.split("}")[-1].lower() == "subfield":
                            code = sub.attrib.get("code", "")
                            val = (sub.text or "").strip()
                            subfields.append((code, val))
                    fields.append((ftag, subfields))

            row = parse_marc_record_fields(fields, control_fields, leader)
            if row.get("title") or row.get("author"):
                rows.append(row)
                for k in row.keys():
                    if row[k]:
                        headers_set.add(k)

    priority_headers = ["title", "author", "isbn", "editorial", "year", "genre", "description", "inventory_code", "location"]
    sorted_headers = [h for h in priority_headers if h in headers_set]
    sorted_headers += sorted([h for h in headers_set if h not in priority_headers])
    return sorted_headers, rows


def parse_uploaded_file(uploaded_file):
    name = (uploaded_file.name or "").lower()
    file_bytes = uploaded_file.read()

    if name.endswith(".xlsx"):
        return parse_xlsx_file(file_bytes)
    elif name.endswith(".bib"):
        return parse_bib_file(file_bytes)
    elif name.endswith((".mrc", ".marc", ".dat")):
        return parse_marc21_bytes(file_bytes)
    elif name.endswith((".xml", ".marcxml")):
        sample_head = file_bytes[:1024].decode("utf-8", errors="ignore").lower()
        if "<record" in sample_head or "<collection" in sample_head or "marc21" in sample_head:
            return parse_marcxml_bytes(file_bytes)
        try:
            return parse_marcxml_bytes(file_bytes)
        except Exception:
            return parse_xlsx_file(file_bytes)
    elif name.endswith((".csv", ".tsv", ".txt")):
        # 1. Verificar si es un archivo binario MARC 21 (ISO 2709)
        if len(file_bytes) >= 24 and file_bytes[:5].isdigit() and b"\x1e" in file_bytes[:1024]:
            try:
                return parse_marc21_bytes(file_bytes)
            except Exception:
                pass

        # 2. Verificar si es XML / MARCXML
        sample_head = file_bytes[:1024].decode("utf-8", errors="ignore")
        sample_head_lower = sample_head.lower()
        if "<record" in sample_head_lower or "<collection" in sample_head_lower:
            try:
                return parse_marcxml_bytes(file_bytes)
            except Exception:
                pass

        # 3. Verificar si es BibTeX
        if re.search(r"@([a-zA-Z]+)\s*\{\s*([^,\s\}]+)\s*,", sample_head):
            try:
                return parse_bib_file(file_bytes)
            except Exception:
                pass

        return parse_csv_file(file_bytes)
    else:
        # Detección inteligente por contenido para extensiones atípicas
        if len(file_bytes) >= 24 and file_bytes[:5].isdigit() and b"\x1e" in file_bytes[:1024]:
            try:
                return parse_marc21_bytes(file_bytes)
            except Exception:
                pass

        sample_head = file_bytes[:1024].decode("utf-8", errors="ignore")
        sample_head_lower = sample_head.lower()
        if "<record" in sample_head_lower or "<collection" in sample_head_lower:
            try:
                return parse_marcxml_bytes(file_bytes)
            except Exception:
                pass

        if re.search(r"@([a-zA-Z]+)\s*\{\s*([^,\s\}]+)\s*,", sample_head):
            try:
                return parse_bib_file(file_bytes)
            except Exception:
                pass

        try:
            return parse_csv_file(file_bytes)
        except Exception:
            return parse_xlsx_file(file_bytes)


def auto_suggest_mapping(headers):
    synonyms = {
        "title": [
            "título", "titulo", "title", "nombre", "obra", "libro", "denominacion",
            "booktitle", "245", "title_proper", "main_title"
        ],
        "author": [
            "autor", "autores", "author", "authors", "escritor", "creador", "editor",
            "100", "700", "110", "personal_name", "creator"
        ],
        "isbn": [
            "isbn", "isbn-10", "isbn-13", "isbn10", "isbn13", "issn", "codigo de barra",
            "barcode", "020", "standard_number"
        ],
        "editorial": [
            "editorial", "editor", "publisher", "sello", "publicador", "institution",
            "organization", "260", "264", "distributor"
        ],
        "year": [
            "año", "ano", "year", "publicacion", "fecha", "edicion", "date", "008",
            "pub_date", "publication_year"
        ],
        "genre": [
            "genero", "género", "genre", "categoria", "categoría", "materia", "tema",
            "subject", "keywords", "keyword", "650", "655", "topical_term"
        ],
        "inventory_code": [
            "codigo", "código", "codigo de inventario", "inventario", "sig", "item",
            "ejemplar", "citation_key", "barcode", "082", "090", "852", "001",
            "control_number", "signatura", "call_number"
        ],
        "location": [
            "ubicacion", "ubicación", "estante", "location", "sector", "sala",
            "posicion", "dónde está", "donde esta", "address", "shelving", "holding"
        ],
        "description": [
            "descripcion", "descripción", "description", "sinopsis", "resumen",
            "nota", "info", "abstract", "note", "annote", "520", "500", "summary"
        ],
    }

    mapping = {}
    for folium_field, syn_list in synonyms.items():
        for h in headers:
            normalized_h = h.lower().strip()
            if any(syn in normalized_h for syn in syn_list):
                mapping[folium_field] = h
                break
    return mapping


class CatalogImporterPreviewView(APIView):
    """
    POST /api/v1/importer/preview/
    Lee el archivo subido, detecta columnas y devuelve las primeras filas de muestra con sugerencia de mapeo.
    """
    permission_classes = [IsLibrarianOrAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"detail": "No se adjuntó ningún archivo para procesar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            headers, rows = parse_uploaded_file(uploaded_file)
        except Exception as err:
            return Response(
                {"detail": f"Error al leer el archivo: {str(err)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not headers or not rows:
            return Response(
                {"detail": "El archivo está vacío o no contiene filas con datos válidos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggested = auto_suggest_mapping(headers)

        return Response({
            "filename": uploaded_file.name,
            "total_rows": len(rows),
            "headers": headers,
            "suggested_mapping": suggested,
            "sample_rows": rows[:5],
        }, status=status.HTTP_200_OK)


class CatalogImporterSimulateView(APIView):
    """
    POST /api/v1/importer/simulate/
    Realiza un dry-run (simulación) del archivo mapeado:
    Verifica cuántos libros nuevos se crearán, cuántos coinciden con el catálogo existente
    y cuántas filas presentan inconsistencias.
    """
    permission_classes = [IsLibrarianOrAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        mapping_raw = request.data.get("mapping", "{}")
        options_raw = request.data.get("options", "{}")

        if not uploaded_file:
            return Response(
                {"detail": "No se adjuntó ningún archivo para procesar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            mapping = json.loads(mapping_raw) if isinstance(mapping_raw, str) else mapping_raw
        except Exception:
            return Response(
                {"detail": "El mapa de campos recibido no tiene un formato JSON válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        options = parse_importer_options(options_raw)

        try:
            _, rows = parse_uploaded_file(uploaded_file)
        except Exception as err:
            return Response(
                {"detail": f"Error al leer el archivo: {str(err)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title_col = mapping.get("title")
        author_col = mapping.get("author")
        isbn_col = mapping.get("isbn")
        editorial_col = mapping.get("editorial")
        year_col = mapping.get("year")
        genre_col = mapping.get("genre")

        if not title_col or not author_col:
            return Response(
                {"detail": "Es obligatorio mapear al menos las columnas de Título y Autor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_rows = 0
        new_books_count = 0
        existing_books_count = 0
        errors = []
        preview_items = []

        # Catálogo de ISBNs y títulos existentes en memoria para comparación rápida (incluye duplicados del mismo archivo y tandas previas)
        existing_isbns = set(
            isbn for isbn in Book.objects.filter(deleted_at__isnull=True).values_list("isbn", flat=True) if isbn
        )
        existing_isbns.update(str(x) for x in options.get("seen_isbns", []) if x)
        existing_titles_lower = set(
            t[:45].lower() for t in Book.objects.filter(deleted_at__isnull=True).values_list("title", flat=True) if t
        )
        existing_titles_lower.update(str(t)[:45].lower() for t in options.get("seen_titles", []) if t)
        discovered_isbns = []
        discovered_titles = []

        for idx, row in enumerate(rows, start=2): # Comienza en 2 contando la cabecera
            title_val = _clean_str(row.get(title_col, ""))
            author_val = _clean_str(row.get(author_col, ""))
            isbn_val = _clean_isbn(row.get(isbn_col, "")) if isbn_col else None

            # Descartar filas completamente vacías o fantasma (ej. filas con fórmulas al final del Excel)
            if not title_val and not author_val:
                continue

            if not title_val:
                reason_msg = "La fila contiene datos pero no tiene título especificado."
                errors.append({
                    "row": idx,
                    "reason": reason_msg,
                    "error": reason_msg,
                    "data": row,
                })
                continue

            if not author_val:
                author_val = "Autor no especificado"

            valid_rows += 1

            clean_title_lower = title_val[:45].lower()
            is_existing = False
            if isbn_val and isbn_val in existing_isbns:
                is_existing = True
            elif clean_title_lower in existing_titles_lower:
                is_existing = True

            if is_existing:
                existing_books_count += 1
            else:
                new_books_count += 1
                if isbn_val:
                    existing_isbns.add(isbn_val)
                    if len(discovered_isbns) < 5000:
                        discovered_isbns.append(isbn_val)
                existing_titles_lower.add(clean_title_lower)
                if len(discovered_titles) < 5000:
                    discovered_titles.append(clean_title_lower)

            if len(preview_items) < 6:
                parsed_authors = split_and_clean_authors(author_val, options["author_format"])
                authors_display_list = [
                    f"{fn} {ln}".strip() if ln != "-" else fn
                    for fn, ln in parsed_authors
                ]
                raw_genre_val = _clean_str(row.get(genre_col, "")) if genre_col else ""
                parsed_genres = split_and_clean_genres(raw_genre_val, options["genre_separator"])

                ed_val = _clean_str(row.get(editorial_col, "")) if editorial_col else ""
                year_val = ""
                if year_col and row.get(year_col):
                    m_y = re.search(r"\b(1\d{3}|20\d{2})\b", _clean_str(row[year_col]))
                    if m_y:
                        year_val = m_y.group(1)

                preview_items.append({
                    "row": idx,
                    "title": title_val[:45],
                    "author": ", ".join(authors_display_list),
                    "authors_list": authors_display_list,
                    "genres_list": parsed_genres,
                    "isbn": isbn_val or "",
                    "editorial": ed_val[:150] if ed_val else "",
                    "year": year_val,
                    "status": "EXISTING" if is_existing else "NEW",
                    "status_simulated": "Existente (añadirá copia)" if is_existing else "Nuevo libro",
                })

        return Response({
            "success": True,
            "total_rows": len(rows),
            "valid_rows": valid_rows,
            "new_books": new_books_count,
            "new_books_count": new_books_count,
            "existing_books": existing_books_count,
            "existing_books_count": existing_books_count,
            "rows_with_errors": len(errors),
            "errors_count": len(errors),
            "error_details": errors[:50],
            "errors": errors[:50], # Límite de 50 para no sobrecargar el payload
            "sample_previews": preview_items,
            "preview_items": preview_items,
            "discovered_isbns": discovered_isbns,
            "discovered_titles": discovered_titles,
        }, status=status.HTTP_200_OK)


class CatalogImporterExecuteView(APIView):
    """
    POST /api/v1/importer/execute/
    Ejecuta la importación en la base de datos de forma transaccional.
    Crea Autores, Géneros, Editoriales, Obras (Book) y Ejemplares Físicos (Item).
    """
    permission_classes = [IsLibrarianOrAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        mapping_raw = request.data.get("mapping", "{}")
        options_raw = request.data.get("options", "{}")

        if not uploaded_file:
            return Response(
                {"detail": "No se adjuntó ningún archivo para procesar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            mapping = json.loads(mapping_raw) if isinstance(mapping_raw, str) else mapping_raw
        except Exception:
            return Response(
                {"detail": "El mapa de campos recibido no tiene un formato JSON válido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        options = parse_importer_options(options_raw)

        try:
            _, rows = parse_uploaded_file(uploaded_file)
        except Exception as err:
            return Response(
                {"detail": f"Error al procesar el archivo: {str(err)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        title_col = mapping.get("title")
        author_col = mapping.get("author")
        isbn_col = mapping.get("isbn")
        editorial_col = mapping.get("editorial")
        year_col = mapping.get("year")
        genre_col = mapping.get("genre")
        code_col = mapping.get("inventory_code")
        location_col = mapping.get("location")
        desc_col = mapping.get("description")

        if not title_col or not author_col:
            return Response(
                {"detail": "Es obligatorio mapear al menos Título y Autor."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        imported_books = 0
        imported_items = 0
        skipped_count = 0
        synthetic_counter = 1

        with transaction.atomic():
            for idx, row in enumerate(rows, start=2):
                title_val = _clean_str(row.get(title_col, ""))
                author_val = _clean_str(row.get(author_col, ""))

                # Descartar filas completamente vacías o fantasma
                if not title_val and not author_val:
                    continue

                if not title_val:
                    skipped_count += 1
                    continue

                if not author_val:
                    author_val = "Autor no especificado"

                # 1. Editorial (búsqueda case-insensitive antes de crear)
                ed_name = _clean_str(row.get(editorial_col, "")) if editorial_col else ""
                ed_name = ed_name[:150] if ed_name else "Editorial Independiente"
                editorial_obj = Editorial.objects.filter(name__iexact=ed_name).first()
                if not editorial_obj:
                    editorial_obj = Editorial.objects.create(name=ed_name)

                # 2. ISBN y Desduplicación de Book
                isbn_val = _clean_isbn(row.get(isbn_col, "")) if isbn_col else None
                book_obj = None

                if isbn_val:
                    book_obj = Book.objects.filter(isbn=isbn_val, deleted_at__isnull=True).first()

                if not book_obj:
                    clean_title = title_val[:45]
                    candidate = Book.objects.filter(
                        title__iexact=clean_title,
                        deleted_at__isnull=True
                    ).first()
                    if candidate:
                        book_obj = candidate

                # Si el libro no existe, lo creamos
                if not book_obj:
                    year_val = None
                    if year_col and row.get(year_col):
                        match_year = re.search(r"\b(1\d{3}|20\d{2})\b", _clean_str(row[year_col]))
                        if match_year:
                            year_val = int(match_year.group(1))

                    desc_val = _clean_str(row.get(desc_col, "")) if desc_col else ""

                    book_obj = Book.objects.create(
                        title=title_val[:45],
                        isbn=isbn_val,
                        editorial=editorial_obj,
                        publication_year=year_val,
                        description=desc_val,
                    )
                    imported_books += 1

                    # 3. Autores (separación inteligente + búsqueda case-insensitive)
                    parsed_authors = split_and_clean_authors(author_val, options["author_format"])
                    for first_name, last_name in parsed_authors:
                        author_obj = Author.objects.filter(
                            name__iexact=first_name,
                            last_name__iexact=last_name,
                        ).first()
                        if not author_obj:
                            author_obj = Author.objects.create(
                                name=first_name,
                                last_name=last_name,
                            )
                        book_obj.authors.add(author_obj)

                # 4. Géneros (división en géneros individuales + búsqueda case-insensitive)
                raw_genre_val = _clean_str(row.get(genre_col, "")) if genre_col else ""
                parsed_genres = split_and_clean_genres(raw_genre_val, options["genre_separator"])
                for g_name in parsed_genres:
                    if g_name == "General" and book_obj.genres.exists():
                        continue
                    genre_obj = Genre.objects.filter(name__iexact=g_name).first()
                    if not genre_obj:
                        genre_obj = Genre.objects.create(name=g_name)
                    book_obj.genres.add(genre_obj)

                # 5. Creación de la copia física (Item)
                code_val = _clean_str(row.get(code_col, "")) if code_col else ""
                if not code_val:
                    code_val = f"INV-{book_obj.id}-{Item.objects.filter(book=book_obj).count() + 1}"
                
                # Garantiza que el código de inventario sea único
                code_clean = re.sub(r"\s+", "-", code_val)[:50]
                if Item.objects.filter(inventory_code=code_clean).exists():
                    code_clean = f"{code_clean[:40]}-{synthetic_counter}"
                    synthetic_counter += 1

                loc_val = _clean_str(row.get(location_col, "")) if location_col else "Estante General"
                loc_val = loc_val[:45] if loc_val else "Estante General"

                Item.objects.create(
                    book=book_obj,
                    inventory_code=code_clean,
                    location=loc_val,
                    status=Item.Status.AVAILABLE,
                )
                imported_items += 1

        return Response({
            "success": True,
            "imported_books": imported_books,
            "imported_items": imported_items,
            "skipped_rows": skipped_count,
            "message": f"Se importaron con éxito {imported_books} obras y {imported_items} ejemplares físicos.",
        }, status=status.HTTP_201_CREATED)
