# -*- coding: utf-8 -*-
"""
Comando de seeding para Folium API.

Uso:
    python manage.py seed_data            # crea los datos (no duplica si ya existen)
    python manage.py seed_data --flush    # borra los datos de la app y vuelve a crear todo

Con Docker:
    docker compose exec web python manage.py seed_data
"""
import random
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.core.files.images import ImageFile

from django.core.management.base import CommandError

from folium_api.models import Author, Genre, Book, Item, Loan, Reservation, Review, Editorial

User = get_user_model()

# Carpeta con los archivos fuente de portadas (se versiona en git).
# El seed las copia a MEDIA_ROOT/books/covers/ vía cover_image.save(),
# nunca escribe la ruta a mano.
COVERS_DIR = Path(__file__).resolve().parent.parent.parent / "seed_assets" / "covers"
COVER_EXTENSIONS = [".webp", ".jpg", ".jpeg", ".png"]


def _find_cover_file(isbn):
    """Busca en COVERS_DIR un archivo llamado '<isbn>.<ext>'. Devuelve el Path
    si existe, o None si el libro no tiene portada disponible."""
    for ext in COVER_EXTENSIONS:
        candidate = COVERS_DIR / f"{isbn}{ext}"
        if candidate.exists():
            return candidate
    return None


def _check_max_length(model, field_name, value, context):
    """Lanza un error claro si `value` no entra en el campo del modelo,
    en vez de dejar que PostgreSQL tire un traceback críptico."""
    max_length = model._meta.get_field(field_name).max_length
    if max_length and len(value) > max_length:
        raise CommandError(
            f"'{value}' ({len(value)} caracteres) excede el máximo de "
            f"{model.__name__}.{field_name} ({max_length} caracteres). Contexto: {context}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Datos base
# ─────────────────────────────────────────────────────────────────────────────

GENEROS = [
    ("Realismo mágico", "Obras donde lo fantástico se integra con naturalidad en la realidad cotidiana."),
    ("Distopía", "Narrativa que retrata sociedades futuras opresivas o deshumanizadas."),
    ("Clásico", "Obras consagradas por la crítica y el paso del tiempo."),
    ("Fábula", "Relatos breves con enseñanza moral, a menudo protagonizados por elementos simbólicos."),
    ("Aventura", "Historias centradas en viajes, exploración y peligros."),
    ("Romance", "Narrativa centrada en relaciones amorosas."),
    ("Terror", "Obras diseñadas para provocar miedo o inquietud."),
    ("Fantasía", "Narrativa ambientada en mundos con elementos mágicos o sobrenaturales."),
    ("Ciencia ficción", "Narrativa basada en avances científicos y tecnológicos, reales o especulativos."),
    ("Misterio", "Tramas centradas en la resolución de un enigma o crimen."),
    ("Historia", "Obras de no ficción centradas en hechos históricos."),
    ("Biografía", "Relatos de no ficción sobre la vida de una persona."),
    ("Filosofía", "Obras centradas en la reflexión sobre el conocimiento y la existencia."),
    ("Drama", "Narrativa centrada en conflictos humanos profundos."),
    ("Juvenil", "Obras dirigidas principalmente a un público joven."),
    ("Cuento de hadas", "Relatos populares breves con elementos mágicos, a menudo de tradición oral.")
]

# (título, [(nombre, apellido), ...], [géneros], año, isbn13, descripción)
LIBROS = [
    ("Cien años de soledad",
            [("Gabriel", "García Márquez")], ["Realismo mágico", "Clásico"], 1967, "9780307474728", "La saga de la familia Buendía en el pueblo mítico de Macondo."),
    ("Crónica de una muerte anunciada", 
            [("Gabriel", "García Márquez")], ["Drama", "Clásico"], 1981, "9780307389684", "La reconstrucción de un crimen anunciado y nunca evitado."),
    ("El amor en los tiempos del cólera", 
            [("Gabriel", "García Márquez")], ["Romance", "Clásico"], 1985, "9780307389732", "Una historia de amor que resiste el paso de más de cincuenta años."),
    ("1984", 
            [("George", "Orwell")], ["Distopía", "Ciencia ficción"], 1949, "9780451524935", "Winston Smith vive bajo la vigilancia total del Gran Hermano."),
    ("Rebelión en la granja", 
            [("George", "Orwell")], ["Fábula", "Distopía"], 1945, "9780451526342", "Los animales de una granja se rebelan contra sus dueños humanos."),
    ("Don Quijote de la Mancha", 
            [("Miguel de", "Cervantes")], ["Clásico", "Aventura"], 1605, "9788420412146", "Las andanzas del ingenioso hidalgo y su fiel escudero Sancho Panza."),
    ("El Principito", 
            [("Antoine de", "Saint-Exupéry")], ["Fábula", "Juvenil"], 1943, "9780156012195", "Un aviador perdido en el desierto conoce a un pequeño príncipe de otro planeta."),
    ("Rayuela", 
            [("Julio", "Cortázar")], ["Clásico", "Drama"], 1963, "9788437604572", "Una novela experimental que puede leerse en múltiples órdenes."),
    ("Orgullo y prejuicio", 
            [("Jane", "Austen")], ["Romance", "Clásico"], 1813, "9780141439518", "Elizabeth Bennet y el orgulloso señor Darcy en la Inglaterra rural."),
    ("Matar a un ruiseñor", 
            [("Harper", "Lee")], ["Drama", "Clásico"], 1960, "9780061120084", "La infancia de Scout Finch en el sur racialmente dividido de Estados Unidos."),
    ("Fahrenheit 451", 
            [("Ray", "Bradbury")], ["Distopía", "Ciencia ficción"], 1953, "9781451673319", "Un futuro donde los bomberos queman libros en lugar de apagar incendios."),
    ("Un mundo feliz", 
            [("Aldous", "Huxley")], ["Distopía", "Ciencia ficción"], 1932, "9780060850524", "Una sociedad futura organizada según castas genéticas y felicidad artificial."),
    ("Frankenstein", 
            [("Mary", "Shelley")], ["Terror", "Clásico"], 1818, "9780486282114", "El doctor Victor Frankenstein y la criatura que él mismo creó."),
    ("Drácula", 
            [("Bram", "Stoker")], ["Terror", "Clásico"], 1897, "9780486411095", "El conde Drácula y la lucha por detener su llegada a Inglaterra."),
    ("El señor de los anillos", 
            [("J.R.R.", "Tolkien")], ["Fantasía", "Aventura"], 1954, "9780618346257", "Frodo Bolsón emprende el viaje para destruir el Anillo Único."),
    ("El hobbit", 
            [("J.R.R.", "Tolkien")], ["Fantasía", "Aventura"], 1937, "9788445077528", "Bilbo Bolsón se une a una compañía de enanos en busca de un tesoro."),
    ("Harry Potter y la piedra filosofal", 
            [("J.K.", "Rowling")], ["Fantasía", "Juvenil"], 1997, "9788478884452", "Un niño descubre que es mago y comienza su formación en Hogwarts."),
    ("Los juegos del hambre", 
            [("Suzanne", "Collins")], ["Distopía", "Juvenil"], 2008, "9780439023528", "Katniss Everdeen participa en un mortal torneo televisado."),
    ("Crimen y castigo", 
            [("Fiódor", "Dostoievski")], ["Drama", "Clásico"], 1866, "9780486415871", "Raskólnikov comete un asesinato y enfrenta las consecuencias morales."),
    ("Anna Karenina", 
            [("León", "Tolstói")], ["Romance", "Clásico"], 1877, "9780143035008", "El destino trágico de Anna Karenina en la sociedad aristocrática rusa."),
    ("La metamorfosis", 
            [("Franz", "Kafka")], ["Clásico", "Drama"], 1915, "9788420674609", "Gregorio Samsa despierta convertido en un enorme insecto."),
    ("El gran Gatsby", 
            [("F. Scott", "Fitzgerald")], ["Clásico", "Drama"], 1925, "9780743273565", "El misterioso millonario Jay Gatsby y su obsesión por el pasado."),
    ("Moby Dick", 
            [("Herman", "Melville")], ["Aventura", "Clásico"], 1851, "9780142437247", "La obsesiva persecución del capitán Ahab a la ballena blanca."),
    ("Sapiens: De animales a dioses", 
            [("Yuval Noah", "Harari")], ["Historia", "Filosofía"], 2011, "9780062316097", "Un recorrido por la historia de la especie humana."),
    ("Breve historia del tiempo", 
            [("Stephen", "Hawking")], ["Historia", "Filosofía"], 1988, "9780553380163", "Una explicación accesible sobre el origen y la naturaleza del universo."),
    ("El alquimista", 
            [("Paulo", "Coelho")], ["Fábula", "Aventura"], 1988, "9780061122415", "Un pastor andaluz viaja a Egipto en busca de un tesoro y su leyenda personal."),
    ("Los detectives salvajes", 
            [("Roberto", "Bolaño")], ["Clásico", "Drama"], 1998, "9788439709819", "Dos jóvenes poetas recorren México y el mundo tras la pista de una poeta perdida."),
    ("La sombra del viento", 
            [("Carlos", "Ruiz Zafón")], ["Misterio", "Drama"], 2001, "9788408043645", "Un joven descubre un libro maldito en el Cementerio de los Libros Olvidados."),
    ("Ficciones", 
            [("Jorge Luis", "Borges")], ["Clásico", "Fantasía"], 1944, "9788420633133", "Una colección de cuentos que exploran laberintos, espejos e infinitos."),
    ("Veinte mil leguas de viaje submarino", 
            [("Julio", "Verne")], ["Aventura", "Ciencia ficción"], 1870, "9788491050939", "El capitán Nemo y las profundidades del océano a bordo del Nautilus."),
    ("Neuromante", 
            [("William", "Gibson")], ["Ciencia ficción"], 1984, "9788445076828", "Un hacker es contratado para un último y peligroso trabajo en el ciberespacio."),
    ("Dune", 
            [("Frank", "Herbert")], ["Ciencia ficción", "Aventura"], 1965, "9780441172719", "Paul Atreides y la lucha por el control del planeta desértico Arrakis."),
    ("El código Da Vinci", 
            [("Dan", "Brown")], ["Misterio", "Aventura"], 2003, "9780307474278", "Un simbólogo investiga un asesinato ligado a un antiguo secreto religioso."),
    ("La casa de los espíritus", 
            [("Isabel", "Allende")], ["Realismo mágico", "Drama"], 1982, "9788401341847", "Cuatro generaciones de la familia Trueba narradas con tintes mágicos y políticos."),
    ("Bodas de sangre", 
            [("Federico", "García Lorca")], ["Drama", "Clásico"], 1932, "9788420671370", "Un drama rural sobre el amor, la venganza y el destino trágico de una boda."),
    ("De ratones y hombres", 
            [("John", "Steinbeck")], ["Drama", "Clásico"], 1937,  "9780140177396", "Dos trabajadores itinerantes sueñan con tener su propia tierra en plena Gran Depresión."),
    ("El péndulo de Foucault", 
            [("Umberto", "Eco")], ["Misterio", "Clásico"], 1988,  "9788426418289", "Tres editores crean un plan ficticio que termina escapando a su control."),
    ("Por quién doblan las campanas", 
            [("Ernest", "Hemingway")], ["Drama", "Aventura"], 1940,  "9780684803357", "Un joven estadounidense combate junto a guerrilleros durante la Guerra Civil española."),
    ("Hijo nativo", 
            [("Richard", "Wright")], ["Drama", "Clásico"], 1940,  "9780061148504", "La vida de un joven afroamericano en el Chicago de los años treinta."),
    ("Matadero cinco", 
            [("Kurt", "Vonnegut")], ["Ciencia ficción", "Drama"], 1969,  "9780385333849", "Un soldado queda 'desanclado en el tiempo' tras vivir el bombardeo de Dresde."),
    ("Ada o el ardor", 
            [("Vladimir", "Nabokov")], ["Romance", "Clásico"], 1969,  "9780679725220", "Una historia de amor entre dos primos narrada como una crónica familiar."),
    ("El guardián entre el centeno", 
            [("J.D.", "Salinger")], ["Drama", "Clásico"], 1951,  "9780316769488", "Holden Caulfield vaga por Nueva York tras ser expulsado del colegio."),
    ("El día de los trífidos", 
            [("John", "Wyndham")], ["Ciencia ficción", "Terror"], 1951,  "9780140813733", "Plantas carnívoras y ambulantes amenazan a la humanidad tras una lluvia de meteoros."),
    ("El viejo y el mar", 
            [("Ernest", "Hemingway")], ["Aventura", "Clásico"], 1952,  "9780684801223", "Un viejo pescador cubano libra una batalla extenuante contra un enorme pez espada."),
    ("El extranjero", 
            [("Albert", "Camus")], ["Filosofía", "Clásico"], 1942,  "9780679720201", "Meursault enfrenta con indiferencia la muerte de su madre y las consecuencias de un crimen."),
    ("La peste", 
            [("Albert", "Camus")], ["Filosofía", "Drama"], 1947,  "9780679720218", "Una epidemia de peste aísla a la ciudad argelina de Orán del resto del mundo."),
    ("Alicia en el país de las maravillas", 
            [("Lewis", "Carroll")], ["Fantasía", "Juvenil"], 1865,  "9788420412160", "Alicia cae por una madriguera y llega a un mundo absurdo lleno de personajes extraños."),
    ("Alicia a través del espejo", 
            [("Lewis", "Carroll")], ["Fantasía", "Juvenil"], 1871,  "9788420412177", "Alicia atraviesa un espejo y descubre un mundo especular regido por el ajedrez."),
    ("Blancanieves", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Juvenil"], 1812,  "9788420699001", "Una joven perseguida por su madrastra encuentra refugio con siete enanos."),
    ("Cenicienta", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Juvenil"], 1812,  "9788420699002", "Una joven maltratada por su familia asiste a un baile real gracias a la magia."),
    ("Hansel y Gretel", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Terror"], 1812,  "9788420699003", "Dos hermanos abandonados en el bosque encuentran una casa hecha de dulces."),
    ("Rapunzel", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Juvenil"], 1812,  "9788420699004", "Una joven de cabello larguísimo permanece encerrada en una torre sin puertas."),
    ("La bella durmiente", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Romance"], 1812,  "9788420699005", "Una princesa cae bajo un hechizo centenario que solo el amor puede romper."),
    ("Caperucita Roja", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Terror"], 1812,  "9788420699006", "Una niña camino a la casa de su abuela se topa con un lobo astuto."),
    ("Los músicos de Bremen", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Aventura"], 1812,  "9788420699007", "Cuatro animales viejos huyen de sus dueños para formar una banda de músicos."),
    ("El enano saltarín", 
            [("Jacob", "Grimm"), ("Wilhelm", "Grimm")], ["Cuento de hadas", "Fantasía"], 1812,  "9788420699008", "Un misterioso enano ayuda a una joven a hilar oro a cambio de un precio muy alto."),
    ("Estudio en escarlata", 
            [("Arthur Conan", "Doyle")], ["Misterio", "Aventura"], 1887,  "9788420700101", "Sherlock Holmes y el doctor Watson se conocen mientras investigan un extraño asesinato."),
    ("El signo de los cuatro", 
            [("Arthur Conan", "Doyle")], ["Misterio", "Aventura"], 1890,  "9788420700102", "Un tesoro perdido, un pacto secreto y un asesino con una pata de palo desafían a Holmes."),
    ("Las aventuras de Sherlock Holmes", 
            [("Arthur Conan", "Doyle")], ["Misterio"], 1892,  "9788420700103", "Doce relatos cortos donde Holmes resuelve enigmas con su método de observación y deducción."),
    ("Las memorias de Sherlock Holmes", 
            [("Arthur Conan", "Doyle")], ["Misterio"], 1894,  "9788420700104", "Nuevos casos de Holmes, incluido su enfrentamiento final con el profesor Moriarty."),
    ("El sabueso de los Baskerville", 
            [("Arthur Conan", "Doyle")], ["Misterio", "Terror"], 1902,  "9788420700105", "Una maldición familiar y un sabueso espectral aterrorizan los páramos de Devon."),
    ("El regreso de Sherlock Holmes", 
            [("Arthur Conan", "Doyle")], ["Misterio"], 1905,  "9788420700106", "Holmes reaparece tras su supuesta muerte para resolver una nueva tanda de casos."),
    ("El valle del terror", 
            [("Arthur Conan", "Doyle")], ["Misterio", "Drama"], 1915,  "9788420700107", "Holmes investiga un asesinato ligado a una sociedad secreta de mineros estadounidenses."),
    ("Los crímenes de la calle Morgue", 
            [("Edgar Allan", "Poe")], ["Misterio", "Terror"], 1841,  "9788420700201", "El detective Auguste Dupin resuelve el brutal asesinato de dos mujeres en París."),
    ("La caída de la casa Usher", 
            [("Edgar Allan", "Poe")], ["Terror"], 1839,  "9788420700202", "Un hombre visita la decadente mansión de un amigo de infancia al borde de la locura."),
    ("El pozo y el péndulo", 
            [("Edgar Allan", "Poe")], ["Terror"], 1842,  "9788420700203", "Un prisionero de la Inquisición enfrenta torturas cada vez más ingeniosas y mortales."),
    ("El misterio de Marie Rogêt", 
            [("Edgar Allan", "Poe")], ["Misterio"], 1842,  "9788420700204", "Dupin investiga a distancia el asesinato de una joven vendedora de perfumes."),
    ("La máscara de la muerte roja", 
            [("Edgar Allan", "Poe")], ["Terror"], 1842,  "9788420700205", "Un príncipe se refugia de una peste mortal en su castillo, sin poder escapar de ella."),
    ("El escarabajo de oro", 
            [("Edgar Allan", "Poe")], ["Misterio", "Aventura"], 1843,  "9788420700206", "Un hombre descifra un mensaje cifrado que lleva hasta un tesoro pirata enterrado."),
    ("El corazón delator", 
            [("Edgar Allan", "Poe")], ["Terror"], 1843,  "9788420700207", "Un asesino es atormentado por el latido imaginario del corazón de su víctima."),
    ("El gato negro", 
            [("Edgar Allan", "Poe")], ["Terror"], 1843,  "9788420700208", "La culpa y la locura de un hombre lo llevan a cometer un crimen imposible de ocultar."),
    ("La carta robada", 
            [("Edgar Allan", "Poe")], ["Misterio"], 1844,  "9788420700209", "Dupin recupera una carta comprometedora escondida a plena vista por su ladrón."),
]

APELLIDOS_LECTORES = ["Gómez", "Fernández", "Rodríguez", "López", "Martínez", "Díaz", "Pérez", "Sánchez"]
NOMBRES_LECTORES = ["Martina", "Lucas", "Sofía", "Mateo", "Valentina", "Joaquín", "Camila", "Tomás"]

UBICACIONES = ["Estante A1", "Estante A2", "Estante B1", "Estante B2", "Estante C1", "Sala de lectura", "Depósito"]


class Command(BaseCommand):
    help = "Carga datos de prueba (seeds) para Folium API: autores, géneros, libros, ítems, usuarios, préstamos, reservas y reseñas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Borra todos los datos existentes de la app antes de crear los nuevos.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Permite ejecutar el comando aunque DEBUG sea False (no recomendado en producción).",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_data está deshabilitado con DEBUG=False. "
                "Solo debe ejecutarse en desarrollo o pasando --force explícitamente."
            )

        random.seed(42)  # datos reproducibles

        self._validate_data_lengths()

        with transaction.atomic():
            if options["flush"]:
                self.stdout.write(self.style.WARNING("Borrando datos existentes de folium_api..."))
                Reservation.objects.all().delete()
                Loan.objects.all().delete()
                Review.objects.all().delete()
                Item.objects.all().delete()
                Book.objects.all().delete()
                Author.objects.all().delete()
                Genre.objects.all().delete()
                User.objects.filter(is_superuser=False).delete()
                User.objects.filter(is_superuser=True, username="admin").delete()

            genres = self._seed_genres()
            authors = self._seed_authors()
            books = self._seed_books(authors, genres)
            items = self._seed_items(books)
            users = self._seed_users()
            if Loan.objects.exists() or Reservation.objects.exists():
                self.stdout.write(
                    self.style.WARNING(
                        "Préstamos o reservas existentes preservados (usá --flush para reiniciar la circulación)."
                    )
                )
            else:
                fully_loaned_books = self._seed_circulation(books, items, users["readers"])
                self._validate_seeded_circulation(fully_loaned_books)
            self._seed_reviews(books, users["readers"])

        self.stdout.write(self.style.SUCCESS("\n✅ Seeds cargados correctamente."))
        self._print_summary(users)

    # ── Validación previa ────────────────────────────────────────────────
    def _validate_data_lengths(self):
        for name, desc in GENEROS:
            _check_max_length(Genre, "name", name, "GENEROS")
        for title, autores, _, _, isbn, desc in LIBROS:
            _check_max_length(Book, "title", title, f"LIBROS: {title}")
            _check_max_length(Book, "isbn", isbn, f"LIBROS: {title}")
            for nombre, apellido in autores:
                _check_max_length(Author, "name", nombre, f"LIBROS/autores: {title}")
                _check_max_length(Author, "last_name", apellido, f"LIBROS/autores: {title}")

    # ── Géneros ──────────────────────────────────────────────────────────
    def _seed_genres(self):
        genres = {}
        for name, desc in GENEROS:
            genre, _ = Genre.objects.get_or_create(name=name, defaults={"description": desc})
            genres[name] = genre
        self.stdout.write(self.style.SUCCESS(f"Géneros: {len(genres)}"))
        return genres

    # ── Autores ──────────────────────────────────────────────────────────
    def _seed_authors(self):
        authors = {}
        seen = set()
        for _, autores, _, _, _, _ in LIBROS:
            for nombre, apellido in autores:
                key = (nombre, apellido)
                if key in seen:
                    continue
                seen.add(key)
                author = Author.objects.filter(name=nombre, last_name=apellido).first()
                if not author:
                    author = Author.objects.create(
                        name=nombre,
                        last_name=apellido,
                        biography="Autor/a de obras reconocidas dentro de la literatura universal.",
                    )
                authors[key] = author
        self.stdout.write(self.style.SUCCESS(f"Autores: {len(authors)}"))
        return authors

    # ── Libros ───────────────────────────────────────────────────────────
    def _seed_books(self, authors, genres):
        books = []
        con_portada = 0
        editorial, _ = Editorial.objects.get_or_create(
            name="Editorial Planeta",
        )
        for title, autores, genero_nombres, year, isbn, desc in LIBROS:
            book, created = Book.objects.get_or_create(
                isbn=isbn,
                defaults={
                    "title": title,
                    "description": desc,
                    "publication_year": year,
                    "editorial": editorial,
                },
            )
            if created:
                book.authors.set([authors[key] for key in autores])
                book.genres.set([genres[g] for g in genero_nombres])

                cover_path = _find_cover_file(isbn)
                if cover_path:
                    with open(cover_path, "rb") as f:
                        # .save() copia el archivo a MEDIA_ROOT/books/covers/
                        # y guarda la ruta relativa en el campo; no hay que
                        # armar ese path a mano.
                        book.cover_image.save(cover_path.name, ImageFile(f), save=True)
                    con_portada += 1
            else:
                # Si el libro ya existía pero no tenía portada asignada
                if not book.cover_image:
                    cover_path = _find_cover_file(isbn)
                    if cover_path:
                        with open(cover_path, "rb") as f:
                            book.cover_image.save(cover_path.name, ImageFile(f), save=True)
                        con_portada += 1
                else:
                    con_portada += 1
            books.append(book)
        self.stdout.write(
            self.style.SUCCESS(f"Libros: {len(books)} (con portada: {con_portada})")
        )
        return books

    # ── Ítems (copias físicas) ──────────────────────────────────────────
    def _seed_items(self, books):
        code_n = 1
        for book in books:
            n_copias = random.choice([1, 2, 2, 3])  # mayoría con 2 copias
            for _ in range(n_copias):
                code = f"INV-{code_n:05d}"
                code_n += 1
                item, created = Item.objects.get_or_create(
                    inventory_code=code,
                    defaults={
                        "book": book,
                        "status": Item.Status.AVAILABLE,
                        "location": random.choice(UBICACIONES),
                    },
                )
        items = list(
            Item.objects.filter(book__in=books)
            .select_related("book")
            .order_by("inventory_code")
        )
        self.stdout.write(self.style.SUCCESS(f"Ítems (copias): {len(items)}"))
        return items

    # ── Usuarios ─────────────────────────────────────────────────────────
    def _seed_users(self):
        users = {"admin": None, "librarians": [], "readers": []}

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "dni": 10000001,
                "email": "admin@folium.com",
                "first_name": "Admin",
                "last_name": "Sistema",
                "rol": User.Rol.LIBRARIAN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password("admin1234")
            admin.save()
        users["admin"] = admin

        bibliotecarios_data = [
            ("mfernandez", "María", "Fernández", "maria.fernandez@folium.com", 20000001),
            ("jperalta", "Juan", "Peralta", "juan.peralta@folium.com", 20000002),
        ]
        for username, first, last, email, dni in bibliotecarios_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "dni": dni,
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "rol": User.Rol.LIBRARIAN,
                    "is_staff": True,
                },
            )
            if created:
                user.set_password("biblio1234")
                user.save()
            users["librarians"].append(user)

        lectores_data = [
            ("mgomez", "Martina", "Gómez", "martina.gomez@correo.com", 30000001),
            ("lrodriguez", "Lucas", "Rodríguez", "lucas.rodriguez@correo.com", 30000002),
        ]
        for username, first, last, email, dni in lectores_data:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "dni": dni,
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "rol": User.Rol.USER,
                },
            )
            if created:
                user.set_password("lector1234")
                user.save()
            users["readers"].append(user)

        # Lectores extra para dar más variedad a reseñas/reservas/préstamos
        for i in range(3, 7):
            first = NOMBRES_LECTORES[i % len(NOMBRES_LECTORES)]
            last = APELLIDOS_LECTORES[i % len(APELLIDOS_LECTORES)]
            username = f"lector{i}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "dni": 30000000 + i,
                    "email": f"{username}@correo.com",
                    "first_name": first,
                    "last_name": last,
                    "rol": User.Rol.USER,
                },
            )
            if created:
                user.set_password("lector1234")
                user.save()
            users["readers"].append(user)

        total = 1 + len(users["librarians"]) + len(users["readers"])
        self.stdout.write(self.style.SUCCESS(
            f"Usuarios: {total} (1 admin, {len(users['librarians'])} bibliotecarios, {len(users['readers'])} lectores)"
        ))
        return users

    # ── Reservas y préstamos ─────────────────────────────────────────────
    def _seed_circulation(self, books, items, readers):
        now = timezone.now()
        items_by_book = {}
        for item in items:
            items_by_book.setdefault(item.book_id, []).append(item)

        used_pairs = set()

        def reserve_user_pair(book):
            eligible_readers = [
                reader for reader in readers
                if (reader.id, book.id) not in used_pairs
            ]
            if not eligible_readers:
                raise CommandError(
                    f"No hay usuarios disponibles para crear otra reserva de '{book.title}'."
                )
            user = random.choice(eligible_readers)
            used_pairs.add((user.id, book.id))
            return user

        def create_accepted_reservation_and_loan(item, loan_status, damaged=False):
            book = item.book
            user = reserve_user_pair(book)
            Reservation.objects.create(
                book=book,
                user=user,
                status=Reservation.StatusReservation.COMPLETED,
                expires_at=now + timedelta(days=random.randint(2, 10)),
            )

            if loan_status == "returned":
                loaned_at = now - timedelta(days=random.randint(30, 60))
                due_at = loaned_at + timedelta(days=14)
                returned_at = loaned_at + timedelta(days=random.randint(3, 13))
                item.status = (
                    Item.Status.DAMAGED if damaged else Item.Status.AVAILABLE
                )
            elif loan_status == "overdue":
                loaned_at = now - timedelta(days=random.randint(20, 40))
                due_at = loaned_at + timedelta(days=14)
                returned_at = None
                item.status = Item.Status.LOANED
            else:
                loaned_at = now - timedelta(days=random.randint(1, 13))
                due_at = loaned_at + timedelta(days=14)
                returned_at = None
                item.status = Item.Status.LOANED

            Loan.objects.create(
                item=item,
                user=user,
                loaned_at=loaned_at,
                due_at=due_at,
                returned_at=returned_at,
            )
            item.save(update_fields=["status", "updated_at"])

        eligible_full_books = [
            book for book in books if len(items_by_book.get(book.id, [])) >= 2
        ]
        fully_loaned_books = random.sample(
            eligible_full_books, k=min(3, len(eligible_full_books))
        )
        fully_loaned_ids = {book.id for book in fully_loaned_books}
        loaned_item_ids = set()
        loan_counts = {"returned": 0, "overdue": 0, "active": 0}

        # Algunos libros quedan sin copias disponibles: todos sus ejemplares
        # tienen un préstamo abierto, vencido o todavía vigente.
        for book in fully_loaned_books:
            for item in items_by_book[book.id]:
                loan_status = random.choice(["overdue", "active"])
                create_accepted_reservation_and_loan(item, loan_status)
                loan_counts[loan_status] += 1
                loaned_item_ids.add(item.id)

        remaining_items = [item for item in items if item.id not in loaned_item_ids]
        scenario_items = {
            "returned": random.sample(remaining_items, k=min(6, len(remaining_items))),
        }
        selected_ids = {item.id for item in scenario_items["returned"]}
        remaining_items = [item for item in remaining_items if item.id not in selected_ids]
        scenario_items["overdue"] = random.sample(
            remaining_items, k=min(5, len(remaining_items))
        )
        selected_ids.update(item.id for item in scenario_items["overdue"])
        remaining_items = [item for item in remaining_items if item.id not in selected_ids]
        scenario_items["active"] = random.sample(
            remaining_items, k=min(5, len(remaining_items))
        )

        returned_items = scenario_items["returned"]
        damaged_item_ids = set()
        if returned_items:
            damaged_count = max(1, len(returned_items) // 5)
            damaged_item_ids = {
                item.id for item in random.sample(
                    returned_items, k=min(damaged_count, len(returned_items))
                )
            }

        for loan_status, selected_items in scenario_items.items():
            for item in selected_items:
                create_accepted_reservation_and_loan(
                    item,
                    loan_status,
                    damaged=item.id in damaged_item_ids,
                )
                loan_counts[loan_status] += 1

        # Estas reservas son independientes: no asignan ni cambian ejemplares.
        standalone_books = [
            book for book in books if book.id not in fully_loaned_ids
        ]
        standalone_counts = {
            Reservation.StatusReservation.PENDING: 0,
            Reservation.StatusReservation.CANCELED: 0,
        }
        for status, count in (
            (Reservation.StatusReservation.PENDING, 8),
            (Reservation.StatusReservation.CANCELED, 5),
        ):
            available_pairs = [
                (book, reader)
                for book in standalone_books
                for reader in readers
                if (reader.id, book.id) not in used_pairs
            ]
            selected_pairs = random.sample(
                available_pairs, k=min(count, len(available_pairs))
            )
            for book, user in selected_pairs:
                used_pairs.add((user.id, book.id))
                Reservation.objects.create(
                    book=book,
                    user=user,
                    status=status,
                    expires_at=now + timedelta(days=random.randint(2, 10)),
                )
                standalone_counts[status] += 1

        self.stdout.write(self.style.SUCCESS(
            "Reservas independientes: "
            f"{standalone_counts[Reservation.StatusReservation.PENDING]} pendientes, "
            f"{standalone_counts[Reservation.StatusReservation.CANCELED]} canceladas; "
            f"reservas aceptadas con préstamo: {sum(loan_counts.values())}"
        ))
        self.stdout.write(self.style.SUCCESS(
            "Préstamos: "
            f"{loan_counts['returned']} devueltos, "
            f"{loan_counts['overdue']} vencidos sin devolver, "
            f"{loan_counts['active']} vigentes"
        ))
        return fully_loaned_books

    def _validate_seeded_circulation(self, fully_loaned_books):
        loans = list(Loan.objects.select_related("item").all())
        completed_reservations = list(
            Reservation.objects.filter(
                status=Reservation.StatusReservation.COMPLETED
            ).values_list("book_id", "user_id")
        )
        loan_pairs = [
            (loan.item.book_id, loan.user_id)
            for loan in loans
        ]
        if sorted(loan_pairs) != sorted(completed_reservations):
            raise CommandError(
                "La seed generó reservas completadas que no coinciden uno a uno "
                "con sus préstamos por libro y usuario."
            )

        for loan in loans:
            if loan.returned_at is None and loan.item.status != Item.Status.LOANED:
                raise CommandError(
                    f"El préstamo abierto #{loan.id} tiene un ejemplar "
                    f"({loan.item.inventory_code}) que no está prestado."
                )
            if (
                loan.returned_at is not None
                and loan.item.status not in {Item.Status.AVAILABLE, Item.Status.DAMAGED}
            ):
                raise CommandError(
                    f"El préstamo devuelto #{loan.id} tiene un ejemplar "
                    f"({loan.item.inventory_code}) en un estado incompatible."
                )

        for book in fully_loaned_books:
            if book.items.exclude(status=Item.Status.LOANED).exists():
                raise CommandError(
                    f"El libro '{book.title}' debía quedar sin ejemplares disponibles."
                )

    # ── Reseñas ──────────────────────────────────────────────────────────
    def _seed_reviews(self, books, readers):
        comentarios_positivos = [
            "Una obra imprescindible, la recomiendo totalmente.",
            "Me atrapó desde la primera página, excelente narrativa.",
            "Un clásico que no defrauda, vale la pena releerlo.",
            "La construcción de los personajes es notable.",
        ]
        comentarios_mixtos = [
            "Buena lectura, aunque el ritmo decae en el medio.",
            "Interesante, pero esperaba un poco más del final.",
            "Está bien escrito, aunque no es para todos los gustos.",
        ]
        comentarios_negativos = [
            "No conectó conmigo, me costó terminarlo.",
            "Esperaba más después de tanta recomendación.",
        ]

        count = 0
        used_pairs = set()
        sample_books = random.sample(books, k=min(20, len(books)))

        for book in sample_books:
            user = random.choice(readers)
            if (user.id, book.id) in used_pairs:
                continue
            used_pairs.add((user.id, book.id))

            rating = random.choices([5, 4, 3, 2, 1], weights=[35, 30, 20, 10, 5])[0]
            if rating >= 4:
                comment = random.choice(comentarios_positivos)
            elif rating == 3:
                comment = random.choice(comentarios_mixtos)
            else:
                comment = random.choice(comentarios_negativos)

            if not Review.objects.filter(book=book, user=user).exists():
                Review.objects.create(
                    book=book,
                    user=user,
                    rating=rating,
                    comment=comment,
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Reseñas: {count}"))

    # ── Resumen final ────────────────────────────────────────────────────
    def _print_summary(self, users):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CREDENCIALES DE PRUEBA"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"  Admin           -> usuario: admin        | contraseña: admin1234")
        for u in users["librarians"]:
            self.stdout.write(f"  Bibliotecario   -> usuario: {u.username:<12} | contraseña: biblio1234")
        for u in users["readers"][:2]:
            self.stdout.write(f"  Lector          -> usuario: {u.username:<12} | contraseña: lector1234")
        self.stdout.write("  (hay 4 lectores adicionales: lector3, lector4, lector5, lector6 con la misma contraseña)")
        self.stdout.write("=" * 60)
