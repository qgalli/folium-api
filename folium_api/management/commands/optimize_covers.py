"""
Comando de administración para migrar y optimizar todas las portadas existentes a WebP.

Uso:
    python manage.py optimize_covers
    python manage.py optimize_covers --files-only
"""

from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, transaction

from folium_api.image_utils import optimize_covers_directory
from folium_api.models import Book

SEED_COVERS_DIR = Path(__file__).resolve().parent.parent.parent / "seed_assets" / "covers"


class Command(BaseCommand):
    help = (
        "Convierte y comprime todas las portadas en media/books/covers/ y seed_assets/covers/ "
        "a formato WebP optimizado (<=600x900px) y sincroniza las rutas en la base de datos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--files-only",
            action="store_true",
            help="Optimiza únicamente los archivos en disco sin consultar la base de datos.",
        )
        parser.add_argument(
            "--keep-originals",
            action="store_true",
            help="Conserva los archivos .jpg/.jpeg/.png originales además del nuevo .webp.",
        )

    def handle(self, *args, **options):
        files_only = options["files_only"]
        keep_originals = options["keep_originals"]

        media_covers_dir = Path(settings.MEDIA_ROOT) / "books" / "covers"
        target_dirs = [
            ("media/books/covers", media_covers_dir),
            ("seed_assets/covers", SEED_COVERS_DIR),
        ]

        for label, folder in target_dirs:
            total, converted, b_before, b_after = optimize_covers_directory(
                folder, keep_originals=keep_originals
            )
            saved_kb = (b_before - b_after) / 1024.0
            pct = ((b_before - b_after) / b_before * 100.0) if b_before > 0 else 0.0
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{label}] {total} archivos analizados | {converted} optimizados a WebP | "
                    f"{b_before / 1024:.1f} KB -> {b_after / 1024:.1f} KB "
                    f"(ahorro: {saved_kb:.1f} KB / {pct:.1f}%)"
                )
            )

        if not files_only:
            try:
                updated_books = 0
                with transaction.atomic():
                    books_with_cover = Book.objects.exclude(cover_image="").exclude(cover_image__isnull=True)
                    for book in books_with_cover:
                        current_name = str(book.cover_image.name or "")
                        if current_name and not current_name.lower().endswith(".webp"):
                            new_rel_name = str(Path(current_name).with_suffix(".webp")).replace("\\", "/")
                            Book.objects.filter(pk=book.pk).update(cover_image=new_rel_name)
                            updated_books += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[Base de datos] {updated_books} registros de Book actualizados a extensión .webp."
                    )
                )
            except OperationalError as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"[Base de datos] No se pudo conectar a PostgreSQL localmente ({exc.__class__.__name__}). "
                        "Los archivos en disco fueron optimizados y el fallback automático en /media/ "
                        "servirá las versiones .webp de forma transparente."
                    )
                )
