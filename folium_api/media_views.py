"""
Vista optimizada de entrega de archivos multimedia (/media/) para Folium.

Características:
1. Funciona tanto en desarrollo (DEBUG=True) como en contenedores de producción (DEBUG=False)
   cuando no hay un servidor Nginx dedicado sirviendo el volumen de media.
2. Fallback transparente a '.webp': si un cliente o caché antiguo solicita
   '/media/books/covers/9788420699005.jpg' y la imagen ya fue migrada a '.webp',
   sirve automáticamente la versión '.webp'.
3. Fallback secundario a 'seed_assets/covers/' para portadas semilla.
4. Cabeceras de caché inmutable para Edge CDN (Vercel / CloudFront) y soporte condicional
   ETag / Last-Modified (304 Not Modified).
"""

import mimetypes
import os
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.utils.http import http_date, parse_http_date_safe

SEED_COVERS_DIR = Path(__file__).resolve().parent / "seed_assets" / "covers"

MIME_OVERRIDES = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".avif": "image/avif",
}

CDN_CACHE_CONTROL = (
    "public, max-age=31536000, s-maxage=31536000, stale-while-revalidate=2592000, immutable"
)


def _resolve_media_file(rel_path: str) -> Path | None:
    """
    Resuelve de forma segura un archivo dentro de MEDIA_ROOT (o SEED_COVERS_DIR como respaldo),
    aplicando fallback automático a extensión '.webp' si el archivo original fue optimizado.
    """
    media_root = Path(settings.MEDIA_ROOT).resolve()
    clean_rel = str(rel_path or "").replace("\\", "/").lstrip("/")
    if not clean_rel or ".." in clean_rel.split("/"):
        return None

    candidate = (media_root / clean_rel).resolve()
    try:
        candidate.relative_to(media_root)
    except ValueError:
        return None

    if candidate.is_file():
        return candidate

    # Fallback 1: si pidieron .jpg/.jpeg/.png y ya fue migrado a .webp en MEDIA_ROOT
    webp_candidate = candidate.with_suffix(".webp")
    if webp_candidate.is_file():
        return webp_candidate

    # Fallback 2: si es una portada en books/covers/ y existe en seed_assets/covers/
    if clean_rel.startswith("books/covers/"):
        seed_root = SEED_COVERS_DIR.resolve()
        filename = candidate.name
        for seed_cand in (seed_root / filename, (seed_root / filename).with_suffix(".webp")):
            try:
                seed_cand_resolved = seed_cand.resolve()
                seed_cand_resolved.relative_to(seed_root)
                if seed_cand_resolved.is_file():
                    return seed_cand_resolved
            except ValueError:
                continue

    return None


def serve_optimized_media(request, path: str):
    """
    Sirve archivos de /media/ con cabeceras de CDN, ETag y soporte 304 Not Modified.
    """
    file_path = _resolve_media_file(path)
    if not file_path:
        raise Http404("Archivo multimedia no encontrado.")

    try:
        stat_obj = file_path.stat()
    except OSError:
        raise Http404("No se pudo acceder al archivo multimedia.")

    etag = f'W/"{stat_obj.st_mtime_ns:x}-{stat_obj.st_size:x}"'
    last_modified_Sec = int(stat_obj.st_mtime)

    # Evaluación condicional ETag (If-None-Match)
    inm = request.META.get("HTTP_IF_NONE_MATCH")
    if inm and (inm.strip() == "*" or etag in [t.strip() for t in inm.split(",")]):
        resp_304 = HttpResponseNotModified()
        resp_304["ETag"] = etag
        resp_304["Cache-Control"] = CDN_CACHE_CONTROL
        return resp_304

    # Evaluación condicional Last-Modified (If-Modified-Since)
    ims = parse_http_date_safe(request.META.get("HTTP_IF_MODIFIED_SINCE", ""))
    if ims is not None and last_modified_Sec <= ims:
        resp_304 = HttpResponseNotModified()
        resp_304["ETag"] = etag
        resp_304["Cache-Control"] = CDN_CACHE_CONTROL
        return resp_304

    ext = file_path.suffix.lower()
    content_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    response = FileResponse(open(file_path, "rb"), content_type=content_type)
    response["Content-Length"] = str(stat_obj.st_size)
    response["ETag"] = etag
    response["Last-Modified"] = http_date(stat_obj.st_mtime)
    response["Cache-Control"] = CDN_CACHE_CONTROL
    response["CDN-Cache-Control"] = CDN_CACHE_CONTROL
    response["Vercel-CDN-Cache-Control"] = CDN_CACHE_CONTROL
    response["Access-Control-Allow-Origin"] = "*"
    return response
