"""
Utilidades de optimización y normalización de imágenes para Folium.

Convierte cualquier imagen subida o descargada (JPEG, PNG, GIF, WebP pesado)
a formato WebP optimizado, redimensionando con filtro LANCZOS hasta un máximo
de 600x900 px para minimizar el peso transferido por el CDN sin pérdida visual.
"""

import io
from pathlib import Path
from PIL import Image, ImageOps

MAX_COVER_WIDTH = 600
MAX_COVER_HEIGHT = 900
WEBP_QUALITY = 82
ALREADY_OPTIMIZED_MAX_BYTES = 85 * 1024  # 85 KB


def optimize_image_bytes_to_webp(
    raw_bytes: bytes,
    max_width: int = MAX_COVER_WIDTH,
    max_height: int = MAX_COVER_HEIGHT,
    quality: int = WEBP_QUALITY,
) -> bytes:
    """
    Recibe los bytes crudos de una imagen, corrige su orientación EXIF,
    la redimensiona proporcionalmente dentro de (max_width, max_height)
    y devuelve los bytes codificados en formato WebP.

    Si la imagen ya está en WebP, dentro de las dimensiones máximas y pesa
    menos de ALREADY_OPTIMIZED_MAX_BYTES, devuelve los bytes originales
    para evitar recodificaciones con pérdida innecesarias.
    """
    if not raw_bytes:
        raise ValueError("No se recibieron bytes de imagen para optimizar.")

    with Image.open(io.BytesIO(raw_bytes)) as img:
        orig_format = (img.format or "").upper()
        width, height = img.size

        if (
            orig_format == "WEBP"
            and width <= max_width
            and height <= max_height
            and len(raw_bytes) <= ALREADY_OPTIMIZED_MAX_BYTES
        ):
            return raw_bytes

        # Corregir rotación según metadatos EXIF (fotos tomadas desde móviles)
        img = ImageOps.exif_transpose(img)

        # Normalizar modo de color para WebP
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Redimensionar manteniendo relación de aspecto (solo achica, nunca agranda)
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        img.save(output, format="WEBP", quality=quality, method=6)
        optimized_bytes = output.getvalue()

        # Si ya era WebP dentro de dimensiones y la recodificación resultó más grande, conservar original
        if (
            orig_format == "WEBP"
            and width <= max_width
            and height <= max_height
            and len(optimized_bytes) >= len(raw_bytes)
        ):
            return raw_bytes

        return optimized_bytes


def optimize_django_image_field(image_field) -> bool:
    """
    Optimiza in-place un ImageFieldFile de Django antes de guardarlo en disco.
    Reemplaza su contenido y extensión por '.webp'.
    Devuelve True si el archivo fue transformado, False si no requería cambios.
    """
    if not image_field or not getattr(image_field, "name", None):
        return False

    try:
        image_field.open("rb")
        raw_bytes = image_field.read()
    except Exception:
        return False

    if not raw_bytes:
        return False

    try:
        webp_bytes = optimize_image_bytes_to_webp(raw_bytes)
    except Exception:
        return False

    current_name = Path(image_field.name).name
    stem = Path(current_name).stem
    new_filename = f"{stem}.webp"

    if current_name.lower().endswith(".webp") and webp_bytes == raw_bytes:
        return False

    from django.core.files.base import ContentFile

    # save=False evita recursión infinita dentro de Model.save()
    image_field.save(new_filename, ContentFile(webp_bytes), save=False)
    return True


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def optimize_covers_directory(directory: Path, keep_originals: bool = False) -> tuple[int, int, int, int]:
    """
    Recorre un directorio de portadas y optimiza cada imagen a .webp (<=600x900px, quality=82).
    Devuelve (total_files, converted_count, bytes_before, bytes_after).
    """
    directory = Path(directory)
    if not directory.exists():
        return (0, 0, 0, 0)

    files = sorted(
        f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    total_files = len(files)
    converted_count = 0
    bytes_before = 0
    bytes_after = 0

    by_stem: dict[str, list[Path]] = {}
    for f in files:
        by_stem.setdefault(f.stem, []).append(f)

    for stem, group in by_stem.items():
        group_sorted = sorted(group, key=lambda p: (0 if p.suffix.lower() != ".webp" else 1))
        src_file = group_sorted[0]

        group_size_before = sum(p.stat().st_size for p in group if p.exists())
        bytes_before += group_size_before

        try:
            raw_bytes = src_file.read_bytes()
            webp_bytes = optimize_image_bytes_to_webp(raw_bytes)
        except Exception:
            bytes_after += group_size_before
            continue

        target_webp = directory / f"{stem}.webp"
        needs_write = (
            not target_webp.exists()
            or target_webp.read_bytes() != webp_bytes
            or len(group) > 1
        )

        if needs_write:
            target_webp.write_bytes(webp_bytes)
            converted_count += 1

        if not keep_originals:
            for p in group:
                if p != target_webp and p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass

        bytes_after += target_webp.stat().st_size if target_webp.exists() else len(webp_bytes)

    return (total_files, converted_count, bytes_before, bytes_after)
