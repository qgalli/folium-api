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
    # Parser nativo de XLSX usando zipfile y ElementTree estándar
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_tree = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_tree.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                shared_strings.append(t.text if t is not None and t.text else "")

        sheet_xml = zf.read("xl/worksheets/sheet1.xml")
        sheet_tree = ET.fromstring(sheet_xml)
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

        matrix = []
        for row in sheet_tree.iter(f"{ns}row"):
            row_vals = []
            for c in row.iter(f"{ns}c"):
                v_el = c.find(f"{ns}v")
                if v_el is None or v_el.text is None:
                    row_vals.append("")
                    continue
                raw_val = v_el.text
                if c.get("t") == "s":
                    idx = int(raw_val)
                    row_vals.append(shared_strings[idx] if idx < len(shared_strings) else "")
                else:
                    row_vals.append(raw_val)
            if any(row_vals):
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


def parse_uploaded_file(uploaded_file):
    name = (uploaded_file.name or "").lower()
    file_bytes = uploaded_file.read()

    if name.endswith(".xlsx"):
        return parse_xlsx_file(file_bytes)
    elif name.endswith((".csv", ".tsv", ".txt")):
        return parse_csv_file(file_bytes)
    else:
        # Intenta primero como CSV
        try:
            return parse_csv_file(file_bytes)
        except Exception:
            return parse_xlsx_file(file_bytes)


def auto_suggest_mapping(headers):
    synonyms = {
        "title": ["título", "titulo", "title", "nombre", "obra", "libro", "denominacion"],
        "author": ["autor", "autores", "author", "authors", "escritor", "creador"],
        "isbn": ["isbn", "isbn-10", "isbn-13", "isbn10", "isbn13", "codigo de barra", "barcode"],
        "editorial": ["editorial", "editor", "publisher", "sello", "publicador"],
        "year": ["año", "ano", "year", "publicacion", "fecha", "edicion", "date"],
        "genre": ["genero", "género", "genre", "categoria", "categoría", "materia", "tema", "subject"],
        "inventory_code": ["codigo", "código", "codigo de inventario", "inventario", "sig", "item", "ejemplar"],
        "location": ["ubicacion", "ubicación", "estante", "location", "sector", "sala", "posicion", "dónde está", "donde esta"],
        "description": ["descripcion", "descripción", "description", "sinopsis", "resumen", "nota", "info"],
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

        # Catálogo de ISBNs y títulos existentes en memoria para comparación rápida
        existing_isbns = set(
            Book.objects.filter(deleted_at__isnull=True).values_list("isbn", flat=True)
        )
        existing_titles = set(
            Book.objects.filter(deleted_at__isnull=True).values_list("title", flat=True)
        )

        for idx, row in enumerate(rows, start=2): # Comienza en 2 contando la cabecera
            title_val = _clean_str(row.get(title_col, ""))
            author_val = _clean_str(row.get(author_col, ""))
            isbn_val = _clean_isbn(row.get(isbn_col, "")) if isbn_col else None

            # Descartar filas completamente vacías o fantasma (ej. filas con fórmulas al final del Excel)
            if not title_val and not author_val:
                continue

            if not title_val:
                errors.append({
                    "row": idx,
                    "reason": "La fila contiene datos pero no tiene título especificado.",
                    "data": row,
                })
                continue

            if not author_val:
                author_val = "Autor no especificado"

            valid_rows += 1

            is_existing = False
            if isbn_val and isbn_val in existing_isbns:
                is_existing = True
            elif title_val.lower() in [t.lower() for t in existing_titles]:
                is_existing = True

            if is_existing:
                existing_books_count += 1
            else:
                new_books_count += 1

            if len(preview_items) < 5:
                preview_items.append({
                    "row": idx,
                    "title": title_val[:45],
                    "author": author_val,
                    "isbn": isbn_val or "Sin ISBN",
                    "status_simulated": "Existente (añadirá copia)" if is_existing else "Nuevo libro",
                })

        return Response({
            "total_rows": len(rows),
            "valid_rows": valid_rows,
            "new_books_count": new_books_count,
            "existing_books_count": existing_books_count,
            "errors_count": len(errors),
            "errors": errors[:50], # Límite de 50 para no sobrecargar el payload
            "preview_items": preview_items,
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
        execution_errors = []

        # Generador de códigos únicos para ítems e ISBNs sintéticos
        base_timestamp = int(timezone.now().timestamp())
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

                # 1. Editorial
                ed_name = _clean_str(row.get(editorial_col, "")) if editorial_col else ""
                ed_name = ed_name[:150] if ed_name else "Editorial Independiente"
                editorial_obj, _ = Editorial.objects.get_or_create(name=ed_name)

                # 2. ISBN y Desduplicación de Book
                isbn_val = _clean_isbn(row.get(isbn_col, "")) if isbn_col else None
                book_obj = None

                if isbn_val:
                    book_obj = Book.objects.filter(isbn=isbn_val, deleted_at__isnull=True).first()

                if not book_obj:
                    # Intenta buscar por Título y primer Autor
                    clean_title = title_val[:45]
                    candidate = Book.objects.filter(
                        title__iexact=clean_title,
                        deleted_at__isnull=True
                    ).first()
                    if candidate:
                        book_obj = candidate

                # Si el libro no existe, lo creamos
                if not book_obj:
                    # Año de publicación (el ISBN queda None si no está presente en el archivo)
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

                    # 3. Autores
                    # Divide si vienen múltiples autores separados por coma o punto y coma
                    authors_list = [a.strip() for a in re.split(r"[,;]+", author_val) if a.strip()]
                    if not authors_list:
                        authors_list = [author_val]

                    for single_author in authors_list[:3]: # Limita a los primeros 3 autores
                        parts = single_author.split()
                        if len(parts) >= 2:
                            first_name = _sanitize_name_text(parts[0], 45, "Autor")
                            last_name = _sanitize_name_text(" ".join(parts[1:]), 45, "-")
                        else:
                            first_name = _sanitize_name_text(single_author, 45, "Autor")
                            last_name = "-"

                        author_obj, _ = Author.objects.get_or_create(
                            name=first_name,
                            last_name=last_name,
                        )
                        book_obj.authors.add(author_obj)

                    # 4. Género
                    genre_name = _clean_str(row.get(genre_col, "")) if genre_col else ""
                    genre_name = genre_name[:100] if genre_name else "General"
                    genre_obj, _ = Genre.objects.get_or_create(name=genre_name)
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
