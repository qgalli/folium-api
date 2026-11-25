from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken
from .models import (
    Author,
    Book,
    Editorial,
    Review,
    Item,
    Loan,
    Reservation,
    Genre,
    LibrarySubscription,
    PaymentTransaction,
    SubscriptionPlan,
    WebhookEventLog,
)
from .passwords import TEMPORARY_PASSWORD_WORDS

User = get_user_model()


class TemporaryPasswordGenerationTests(SimpleTestCase):
    def test_password_word_list_is_unique_and_uses_short_ascii_words(self):
        self.assertGreaterEqual(len(TEMPORARY_PASSWORD_WORDS), 300)
        self.assertEqual(
            len(TEMPORARY_PASSWORD_WORDS),
            len(set(TEMPORARY_PASSWORD_WORDS)),
        )
        self.assertTrue(
            all(
                word.isascii() and word.isalpha() and len(word) <= 6
                for word in TEMPORARY_PASSWORD_WORDS
            )
        )


class TokenRoleClaimTests(APITestCase):
	def assert_token_role(self, user, expected_role):
		response = self.client.post(
			reverse("token_obtain_pair"),
			{"username": user.username, "password": "test-password"},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(set(response.data), {"refresh", "access", "user"})
		self.assertEqual(AccessToken(response.data["access"])["rol"], expected_role)

	def test_superuser_role_claim_is_admin(self):
		user = User.objects.create_user(
			username="admin-superuser-test",
			dni=12345678,
			email="admin-superuser-test@example.com",
			password="test-password",
			rol=User.Rol.LIBRARIAN,
			is_staff=True,
			is_superuser=True,
		)

		self.assert_token_role(user, User.Rol.ADMIN)

	def test_librarian_role_claim(self):
		user = User.objects.create_user(
			username="librarian",
			dni=23456789,
			email="librarian@example.com",
			password="test-password",
			rol=User.Rol.LIBRARIAN,
		)

		self.assert_token_role(user, User.Rol.LIBRARIAN)

	def test_reader_role_claim(self):
		user = User.objects.create_user(
			username="reader",
			dni=34567890,
			email="reader@example.com",
			password="test-password",
			rol=User.Rol.USER,
		)

		self.assert_token_role(user, User.Rol.USER)


class UserDniTests(APITestCase):
	def test_create_user_with_dni_success(self):
		user = User.objects.create_user(
			username="user_with_dni",
			dni=40111222,
			email="user_dni@example.com",
			password="test-password",
		)
		self.assertEqual(user.dni, 40111222)

	def test_duplicate_dni_raises_error(self):
		User.objects.create_user(
			username="user1",
			dni=40999888,
			email="user1@example.com",
			password="test-password",
		)
		from django.db import IntegrityError
		with self.assertRaises(IntegrityError):
			User.objects.create_user(
				username="user2",
				dni=40999888,
				email="user2@example.com",
				password="test-password",
			)

	def test_negative_or_zero_dni_validation(self):
		from django.core.exceptions import ValidationError
		user = User(
			username="invalid_dni",
			dni=-5,
			email="invalid_dni@example.com",
		)
		with self.assertRaises(ValidationError) as ctx:
			user.clean()
		self.assertIn("dni", ctx.exception.message_dict)

	def test_reader_registration_with_dni(self):
		response = self.client.post(
			reverse("folium_api:reader-register"),
			{
				"username": "newreader",
				"dni": 41234567,
				"email": "newreader@example.com",
				"password": "strongPassword123",
				"first_name": "Nuevo",
				"last_name": "Lector",
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data["dni"], 41234567)

		# Intento con DNI duplicado
		duplicate_response = self.client.post(
			reverse("folium_api:reader-register"),
			{
				"username": "anotherreader",
				"dni": 41234567,
				"email": "another@example.com",
				"password": "strongPassword123",
				"first_name": "Otro",
				"last_name": "Lector",
			},
			format="json",
		)
		self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn("dni", duplicate_response.data)

	def test_reader_registration_forces_user_role(self):
		response = self.client.post(
			reverse("folium_api:reader-register"),
			{
				"username": "lector_prueba",
				"dni": 48111222,
				"email": "lector_prueba@example.com",
				"password": "strongPassword123",
				"first_name": "Lector",
				"last_name": "Prueba",
				"rol": "ADMIN",  # Intento de elevar privilegios o valor no estándar como "Usuario"
			},
			format="json",
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data["rol"], User.Rol.USER)

		user = User.objects.get(username="lector_prueba")
		self.assertEqual(user.rol, User.Rol.USER)
		self.assertFalse(user.is_staff)
		self.assertFalse(user.is_superuser)
		self.assertTrue(user.check_password("strongPassword123"))


class RandomBookEndpointTests(APITestCase):
	def setUp(self):
		Item.objects.all().delete()
		Book.objects.all().delete()
		self.editorial = Editorial.objects.create(name="Editorial Sudamericana")
		self.author = Author.objects.create(name="Gabriel", last_name="García Márquez")
		self.book = Book.objects.create(
			title="Cien años de soledad",
			publication_year=1967,
			isbn="9780307474728",
			editorial=self.editorial,
		)
		self.book.authors.add(self.author)

	def test_random_book_unauthenticated_returns_200_and_expected_fields(self):
		"""
		El endpoint /random debe ser accesible sin autenticación y retornar
		(id, titulo, año, tapa, autor).
		"""
		response = self.client.get("/api/v1/random/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		data = response.data
		required_fields = ["id", "title", "year", "cover", "author"]
		for field in required_fields:
			self.assertIn(field, data, f"El campo {field} debe estar presente en la respuesta")

		self.assertEqual(data["id"], self.book.id)
		self.assertEqual(data["title"], "Cien años de soledad")
		self.assertEqual(data["year"], 1967)
		self.assertEqual(data["author"], "Gabriel García Márquez")

	def test_random_book_empty_catalog_returns_404(self):
		"""
		Si el catálogo está vacío, debe responder con 404.
		"""
		Item.objects.all().delete()
		Book.objects.all().delete()
		response = self.client.get("/api/v1/random/")
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BookRecommendationEndpointTests(APITestCase):
	def setUp(self):
		Item.objects.all().delete()
		Book.objects.all().delete()
		self.editorial = Editorial.objects.create(name="Editorial Sur")
		self.author = Author.objects.create(name="Jorge Luis", last_name="Borges")
		self.user = User.objects.create_user(
			username="reviewer1",
			email="rev1@example.com",
			dni=77711122,
			password="test-password",
		)
		self.user2 = User.objects.create_user(
			username="reviewer2",
			email="rev2@example.com",
			dni=77711123,
			password="test-password",
		)

		# Creamos libros con diferentes calificaciones
		self.book_top = Book.objects.create(
			title="Ficciones",
			publication_year=1944,
			isbn="9788420633121",
			editorial=self.editorial,
		)
		self.book_top.authors.add(self.author)

		self.book_mid = Book.objects.create(
			title="El Aleph",
			publication_year=1949,
			isbn="9788420633138",
			editorial=self.editorial,
		)
		self.book_mid.authors.add(self.author)

		self.book_low = Book.objects.create(
			title="El libro de arena",
			publication_year=1975,
			isbn="9788420633145",
			editorial=self.editorial,
		)
		self.book_low.authors.add(self.author)

		# Reseñas
		Review.objects.create(book=self.book_top, user=self.user, rating=5)
		Review.objects.create(book=self.book_mid, user=self.user, rating=3)
		Review.objects.create(book=self.book_low, user=self.user, rating=1)

	def test_recommendation_unauthenticated_returns_top_books(self):
		"""
		El endpoint /recommendation debe ser accesible sin login, retornar
		hasta 10 libros ordenados de mejor a peor rating, conteniendo
		(id, titulo, año, tapa, autor).
		"""
		response = self.client.get("/api/v1/recommendation/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIsInstance(response.data, list)
		self.assertLessEqual(len(response.data), 10)

		# Verificar los campos obligatorios en cada libro
		required_fields = ["id", "title", "year", "cover", "author"]
		for item in response.data:
			for field in required_fields:
				self.assertIn(field, item, f"El campo {field} debe estar presente en cada libro")

		# El primer libro debe ser 'Ficciones' (rating 5)
		self.assertEqual(response.data[0]["id"], self.book_top.id)
		self.assertEqual(response.data[0]["title"], "Ficciones")
		self.assertEqual(response.data[0]["year"], 1944)
		self.assertEqual(response.data[0]["author"], "Jorge Luis Borges")

		# El segundo debe ser 'El Aleph' (rating 3)
		self.assertEqual(response.data[1]["id"], self.book_mid.id)

	def test_recommendation_excludes_deleted_reviews_and_soft_deleted_books(self):
		"""
		Las reseñas eliminadas (deleted_at no nulo) o libros eliminados
		no deben influir ni aparecer en el listado.
		"""
		from django.utils import timezone
		# Eliminamos la reseña de Ficciones
		rev = Review.objects.get(book=self.book_top)
		rev.deleted_at = timezone.now()
		rev.save()

		# Marcamos el libro 'El Aleph' como eliminado
		self.book_mid.deleted_at = timezone.now()
		self.book_mid.save()

		response = self.client.get("/api/v1/recommendation/")
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		returned_ids = [b["id"] for b in response.data]
		# El Aleph no debe aparecer porque fue eliminado
		self.assertNotIn(self.book_mid.id, returned_ids)



class MarcImporterTests(APITestCase):
	def _create_sample_marc_binary(self):
		def make_record(fields):
			body = bytearray()
			directory = bytearray()
			current_offset = 0
			for tag, ind, content in fields:
				field_bytes = bytearray()
				if int(tag) < 10:
					field_bytes.extend(content.encode('utf-8'))
				else:
					field_bytes.extend(ind.encode('utf-8')[:2].ljust(2, b' '))
					for code, val in content:
						field_bytes.append(0x1F)
						field_bytes.extend(code.encode('utf-8')[:1])
						field_bytes.extend(val.encode('utf-8'))
				field_bytes.append(0x1E)
				f_len = len(field_bytes)
				directory.extend(f'{tag:0>3}'.encode('ascii')[:3])
				directory.extend(f'{f_len:0>4}'.encode('ascii')[:4])
				directory.extend(f'{current_offset:0>5}'.encode('ascii')[:5])
				body.extend(field_bytes)
				current_offset += f_len
			directory.append(0x1E)
			base_address = 24 + len(directory)
			total_len = base_address + len(body) + 1
			leader = f'{total_len:0>5}nam a22{base_address:0>5} u 4500'.encode('ascii')
			record = bytearray(leader)
			record.extend(directory)
			record.extend(body)
			record.append(0x1D)
			return bytes(record)

		rec1 = make_record([
			('001', '', 'FOL-0001'),
			('008', '', '850314s1967    ck            000 0 spa  '),
			('020', '  ', [('a', '9780307474728')]),
			('100', '1 ', [('a', 'García Márquez, Gabriel,')]),
			('245', '10', [('a', 'Cien años de soledad /'), ('c', 'Gabriel García Márquez.')]),
			('264', ' 1', [('b', 'Sudamericana,'), ('c', '1967.')]),
			('650', ' 0', [('a', 'Realismo mágico.')]),
			('852', '  ', [('p', 'INV-GABO-01'), ('c', 'Sala A'), ('h', 'Estante 3')]),
			('520', '  ', [('a', 'Obra cumbre de la literatura hispanoamericana.')]),
		])

		rec2 = make_record([
			('001', '', 'FOL-0002'),
			('008', '', '850314s1944    ag            000 0 spa  '),
			('020', '  ', [('a', '9789500419574')]),
			('100', '1 ', [('a', 'Borges, Jorge Luis,')]),
			('245', '10', [('a', 'Ficciones /'), ('c', 'Jorge Luis Borges.')]),
			('264', ' 1', [('b', 'Sur,'), ('c', '1944.')]),
			('650', ' 0', [('a', 'Ficción Filosófica.')]),
			('852', '  ', [('p', 'INV-BORGES-01'), ('c', 'Sector Archivo'), ('h', 'Estantería 4')]),
			('520', '  ', [('a', 'Colección de relatos sobre laberintos.')]),
		])
		return rec1 + rec2

	def test_parse_marc21_binary_success(self):
		from .importer_views import parse_marc21_bytes
		raw_bytes = self._create_sample_marc_binary()
		headers, rows = parse_marc21_bytes(raw_bytes)

		self.assertEqual(len(rows), 2)
		self.assertIn("title", headers)
		self.assertIn("author", headers)
		self.assertIn("isbn", headers)
		self.assertIn("year", headers)

		first = rows[0]
		self.assertEqual(first["title"], "Cien años de soledad")
		self.assertEqual(first["author"], "Gabriel García Márquez")
		self.assertEqual(first["isbn"], "9780307474728")
		self.assertEqual(first["editorial"], "Sudamericana")
		self.assertEqual(first["year"], "1967")
		self.assertEqual(first["genre"], "Realismo mágico")
		self.assertEqual(first["inventory_code"], "INV-GABO-01")

		second = rows[1]
		self.assertEqual(second["title"], "Ficciones")
		self.assertEqual(second["author"], "Jorge Luis Borges")
		self.assertEqual(second["isbn"], "9789500419574")
		self.assertEqual(second["editorial"], "Sur")
		self.assertEqual(second["year"], "1944")

	def test_parse_marcxml_success(self):
		from .importer_views import parse_marcxml_bytes
		xml_data = """<?xml version="1.0" encoding="UTF-8"?>
		<collection xmlns="http://www.loc.gov/MARC21/slim">
		  <record>
		    <controlfield tag="001">FOL-0003</controlfield>
		    <datafield tag="020" ind1=" " ind2=" ">
		      <subfield code="a">9788466331906 (rústica)</subfield>
		    </datafield>
		    <datafield tag="100" ind1="1" ind2=" ">
		      <subfield code="a">Cortázar, Julio,</subfield>
		      <subfield code="d">1914-1984.</subfield>
		    </datafield>
		    <datafield tag="245" ind1="1" ind2="0">
		      <subfield code="a">Rayuela /</subfield>
		      <subfield code="b">una contranovela</subfield>
		    </datafield>
		    <datafield tag="260" ind1=" " ind2=" ">
		      <subfield code="b">Sudamericana,</subfield>
		      <subfield code="c">1963.</subfield>
		    </datafield>
		    <datafield tag="650" ind1=" " ind2="0">
		      <subfield code="a">Novela experimental.</subfield>
		    </datafield>
		    <datafield tag="852" ind1=" " ind2=" ">
		      <subfield code="p">INV-CORTAZAR-01</subfield>
		      <subfield code="c">Sala A</subfield>
		      <subfield code="h">Estante 2</subfield>
		    </datafield>
		  </record>
		</collection>
		""".encode("utf-8")

		headers, rows = parse_marcxml_bytes(xml_data)
		self.assertEqual(len(rows), 1)
		book = rows[0]
		self.assertEqual(book["title"], "Rayuela : una contranovela")
		self.assertEqual(book["author"], "Julio Cortázar")
		self.assertEqual(book["isbn"], "9788466331906")
		self.assertEqual(book["editorial"], "Sudamericana")
		self.assertEqual(book["year"], "1963")
		self.assertEqual(book["genre"], "Novela experimental")
		self.assertEqual(book["inventory_code"], "INV-CORTAZAR-01")
		self.assertEqual(book["location"], "Sala A - Estante 2")

class CatalogPublicReadOnlyTests(APITestCase):
    """
    Pruebas de que la lectura del catálogo es pública y no requiere sesión.
    """

    def setUp(self):
        self.editorial = Editorial.objects.create(name="Editorial Test")
        self.author = Author.objects.create(name="Test", last_name="Autor")
        self.genre = Genre.objects.create(name="Test Genre")
        self.book = Book.objects.create(
            title="Libro Público",
            editorial=self.editorial,
            isbn="9780000000001",
            publication_year=2024,
        )
        self.book.authors.add(self.author)
        self.book.genres.add(self.genre)
        self.reader = User.objects.create_user(
            username="reader-perm",
            dni=99999991,
            email="reader-perm@example.com",
            password="test-password",
            rol=User.Rol.USER,
        )
        self.librarian = User.objects.create_user(
            username="librarian-perm",
            dni=99999992,
            email="librarian-perm@example.com",
            password="test-password",
            rol=User.Rol.LIBRARIAN,
        )

    def test_anon_can_list_books(self):
        response = self.client.get(reverse("folium_api:book-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anon_can_retrieve_book(self):
        response = self.client.get(reverse("folium_api:book-detail", args=[self.book.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anon_can_list_authors(self):
        response = self.client.get(reverse("folium_api:author-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anon_can_list_genres(self):
        response = self.client.get(reverse("folium_api:genre-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anon_can_list_editorials(self):
        response = self.client.get(reverse("folium_api:editorial-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_anon_can_call_book_options(self):
        response = self.client.get(reverse("folium_api:book-options"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reader_cannot_create_editorial(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            reverse("folium_api:editorial-list"),
            {"name": "Editorial No Autorizada"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_librarian_can_create_editorial(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.post(
            reverse("folium_api:editorial-list"),
            {"name": "Editorial Nueva Permitida"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_librarian_can_create_book_with_editorial_name(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.post(
            reverse("folium_api:book-list"),
            {
                "title": "Libro Con Editorial Por Nombre",
                "editorial": "Editorial Creada Al Vuelo",
                "isbn": "9780000000003",
                "authors": [self.author.id],
                "genres": [self.genre.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Editorial.objects.filter(name="Editorial Creada Al Vuelo").exists())
    def test_anon_cannot_create_book(self):
        response = self.client.post(
            reverse("folium_api:book-list"),
            {"title": "No autorizado", "editorial": self.editorial.id},
            format="json",
        )
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_reader_cannot_create_book(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            reverse("folium_api:book-list"),
            {"title": "No autorizado", "editorial": self.editorial.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_librarian_can_create_book(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.post(
            reverse("folium_api:book-list"),
            {
                "title": "Libro Bibliotecario",
                "editorial": self.editorial.id,
                "isbn": "9780000000002",
                "authors": [self.author.id],
                "genres": [self.genre.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_soft_delete_book_excludes_it_from_catalog_and_options(self):
        self.client.force_authenticate(user=self.librarian)
        delete_url = reverse("folium_api:book-detail", args=[self.book.id])
        res_del = self.client.delete(delete_url)
        self.assertEqual(res_del.status_code, status.HTTP_204_NO_CONTENT)

        self.book.refresh_from_db()
        self.assertIsNotNone(self.book.deleted_at)

        # No aparece en el catálogo
        res_list = self.client.get(reverse("folium_api:book-list"))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        book_ids = [b["id"] for b in res_list.data["results"]]
        self.assertNotIn(self.book.id, book_ids)

        # Retorna 404 al consultar detalle
        res_detail = self.client.get(delete_url)
        self.assertEqual(res_detail.status_code, status.HTTP_404_NOT_FOUND)

        # No aparece en options
        res_options = self.client.get(reverse("folium_api:book-options"))
        self.assertEqual(res_options.status_code, status.HTTP_200_OK)
        option_ids = [b["id"] for b in res_options.data]
        self.assertNotIn(self.book.id, option_ids)

    def test_recreating_soft_deleted_book_reactivates_it(self):
        self.client.force_authenticate(user=self.librarian)
        self.book.deleted_at = timezone.now()
        self.book.save(update_fields=["deleted_at"])

        # Intentar volver a dar de alta con el mismo ISBN
        response = self.client.post(
            reverse("folium_api:book-list"),
            {
                "title": "Libro Reactivado",
                "editorial": self.editorial.id,
                "isbn": self.book.isbn,
                "authors": [self.author.id],
                "genres": [self.genre.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.book.refresh_from_db()
        self.assertIsNone(self.book.deleted_at)
        self.assertEqual(self.book.title, "Libro Reactivado")

    def test_restore_action_reactivates_soft_deleted_book(self):
        self.client.force_authenticate(user=self.librarian)
        self.book.deleted_at = timezone.now()
        self.book.save(update_fields=["deleted_at"])

        restore_url = f"/api/v1/book/{self.book.id}/restore/"
        response = self.client.post(restore_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.book.refresh_from_db()
        self.assertIsNone(self.book.deleted_at)

    def test_items_and_loans_stay_private(self):
        response_items = self.client.get(reverse("folium_api:item-list"))
        self.assertIn(response_items.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])
        response_loans = self.client.get(reverse("folium_api:loan-list"))
        self.assertIn(response_loans.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_reader_cannot_read_items_and_librarian_can(self):
        item = Item.objects.create(book=self.book, inventory_code="PERM-ITEM-1")

        self.client.force_authenticate(user=self.reader)
        res_list_reader = self.client.get(reverse("folium_api:item-list"))
        self.assertEqual(res_list_reader.status_code, status.HTTP_403_FORBIDDEN)
        res_detail_reader = self.client.get(reverse("folium_api:item-detail", args=[item.id]))
        self.assertEqual(res_detail_reader.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.librarian)
        res_list_lib = self.client.get(reverse("folium_api:item-list"))
        self.assertEqual(res_list_lib.status_code, status.HTTP_200_OK)
        res_detail_lib = self.client.get(reverse("folium_api:item-detail", args=[item.id]))
        self.assertEqual(res_detail_lib.status_code, status.HTTP_200_OK)


class LoanCounterTests(APITestCase):
    def setUp(self):
        self.librarian = User.objects.create_user(
            username="counter_biblio",
            dni=99887766,
            email="counter_biblio@example.com",
            password="test-password",
            rol=User.Rol.LIBRARIAN,
        )
        self.reader = User.objects.create_user(
            username="existing_reader",
            dni=11223344,
            first_name="Carlos",
            last_name="Perez",
            email="carlos.perez@example.com",
            password="test-password",
            rol=User.Rol.USER,
        )
        self.editorial = Editorial.objects.create(name="Editorial Counter")
        self.author = Author.objects.create(name="Jorge", last_name="Borges")
        self.book = Book.objects.create(
            title="Ficciones",
            editorial=self.editorial,
            isbn="9789871138012",
        )
        self.book.authors.add(self.author)
        self.available_item = Item.objects.create(
            book=self.book,
            inventory_code="FIC-001",
            status=Item.Status.AVAILABLE,
            location="Estante A-1",
        )

    def test_librarian_can_find_user_by_dni(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.get(f"/api/v1/user/by-dni/{self.reader.dni}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["dni"], self.reader.dni)
        self.assertEqual(response.data["username"], "existing_reader")
        self.assertEqual(response.data["active_loans_count"], 0)

    def test_librarian_gets_404_when_user_not_found_by_dni(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.get("/api/v1/user/by-dni/99999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_librarian_can_create_reader(self):
        self.client.force_authenticate(user=self.librarian)
        payload = {
            "dni": 55667788,
            "first_name": "Ana",
            "last_name": "Gomez",
            "email": "ana.gomez@example.com",
        }
        response = self.client.post("/api/v1/user/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["dni"], 55667788)
        self.assertEqual(response.data["rol"], User.Rol.USER)
        temporary_password = response.data["temporary_password"]
        password_parts = temporary_password.split("-")
        self.assertEqual(len(password_parts), 6)
        self.assertTrue(all(word in TEMPORARY_PASSWORD_WORDS for word in password_parts[:5]))
        self.assertTrue(password_parts[-1].isdigit())
        self.assertEqual(len(password_parts[-1]), 4)
        self.assertTrue(User.objects.filter(dni=55667788).exists())
        reader = User.objects.get(dni=55667788)
        self.assertTrue(reader.check_password(temporary_password))
        self.assertNotIn("password", response.data)

        self.client.force_authenticate(user=None)
        login_response = self.client.post(
            "/api/v1/token/",
            {
                "username": response.data["username"],
                "password": temporary_password,
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=reader)
        profile_response = self.client.get("/api/v1/me/")
        self.assertEqual(profile_response.status_code, status.HTTP_200_OK)
        self.assertNotIn("temporary_password", profile_response.data)

    def test_librarian_can_get_available_books_for_loan(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.get("/api/v1/book/available/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        book_data = next(
            (b for b in response.data["results"] if b["id"] == self.book.id),
            None,
        )
        self.assertIsNotNone(book_data)
        self.assertEqual(book_data["available_count"], 1)
        self.assertEqual(book_data["available_items"][0]["inventory_code"], "FIC-001")

    def test_available_books_endpoint_paginates_50_books_by_default(self):
        self.client.force_authenticate(user=self.librarian)
        for index in range(50):
            book = Book.objects.create(
                title=f"Available title {index:02d}",
                editorial=self.editorial,
                isbn=f"978000000{index:04d}",
            )
            Item.objects.create(
                book=book,
                inventory_code=f"PAGE-{index:03d}",
                status=Item.Status.AVAILABLE,
            )

        first_page = self.client.get("/api/v1/book/available/")
        self.assertEqual(first_page.status_code, status.HTTP_200_OK)
        self.assertEqual(first_page.data["count"], 51)
        self.assertEqual(len(first_page.data["results"]), 50)
        self.assertIsNone(first_page.data["previous"])
        self.assertIsNotNone(first_page.data["next"])

        second_page = self.client.get("/api/v1/book/available/?page=2")
        self.assertEqual(second_page.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second_page.data["results"]), 1)
        self.assertIsNotNone(second_page.data["previous"])
        self.assertIsNone(second_page.data["next"])

    def test_available_books_search_does_not_duplicate_multiple_matching_authors(self):
        self.client.force_authenticate(user=self.librarian)
        book = Book.objects.create(
            title="Cuentos tradicionales",
            editorial=self.editorial,
            isbn="9780000000001",
        )
        book.authors.add(
            Author.objects.create(name="Jacob", last_name="Grimm"),
            Author.objects.create(name="Wilhelm", last_name="Grimm"),
        )
        Item.objects.create(
            book=book,
            inventory_code="INV-001",
            status=Item.Status.AVAILABLE,
        )

        response = self.client.get(
            "/api/v1/book/available/",
            {"search": "Grimm"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], book.id)

    def test_librarian_can_create_loan_for_item(self):
        self.client.force_authenticate(user=self.librarian)
        payload = {
            "item": self.available_item.id,
            "user": self.reader.id,
        }
        response = self.client.post("/api/v1/loan/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.available_item.refresh_from_db()
        self.assertEqual(self.available_item.status, Item.Status.LOANED)

    def test_reader_cannot_access_user_management(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.get(f"/api/v1/user/by-dni/{self.reader.dni}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ChangePasswordTests(APITestCase):
    def setUp(self):
        self.reader = User.objects.create_user(
            username="password_reader",
            dni=88776655,
            email="password_reader@example.com",
            password="Original-Reader-Password-289!",
            rol=User.Rol.USER,
        )
        self.librarian = User.objects.create_user(
            username="password_librarian",
            dni=88776656,
            email="password_librarian@example.com",
            password="Original-Librarian-Password-289!",
            rol=User.Rol.LIBRARIAN,
        )
        self.new_password = "Fresh-Account-Password-782!"

    def test_reader_can_change_own_password(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Original-Reader-Password-289!",
                "new_password": self.new_password,
                "confirm_new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password(self.new_password))

    def test_librarian_can_change_own_password(self):
        self.client.force_authenticate(user=self.librarian)
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Original-Librarian-Password-289!",
                "new_password": self.new_password,
                "confirm_new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.librarian.refresh_from_db()
        self.assertTrue(self.librarian.check_password(self.new_password))

    def test_change_password_rejects_wrong_current_password(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Incorrect-Current-Password",
                "new_password": self.new_password,
                "confirm_new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password("Original-Reader-Password-289!"))

    def test_change_password_rejects_mismatched_confirmation(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Original-Reader-Password-289!",
                "new_password": self.new_password,
                "confirm_new_password": "Different-Account-Password-289!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_rejects_password_that_fails_django_validators(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Original-Reader-Password-289!",
                "new_password": "short",
                "confirm_new_password": "short",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password("Original-Reader-Password-289!"))

    def test_change_password_requires_authentication(self):
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Original-Reader-Password-289!",
                "new_password": self.new_password,
                "confirm_new_password": self.new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_change_only_updates_authenticated_user(self):
        self.client.force_authenticate(user=self.reader)
        response = self.client.post(
            "/api/v1/me/change-password/",
            {
                "current_password": "Original-Reader-Password-289!",
                "new_password": self.new_password,
                "confirm_new_password": self.new_password,
                "user_id": self.librarian.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reader.refresh_from_db()
        self.librarian.refresh_from_db()
        self.assertTrue(self.reader.check_password(self.new_password))
        self.assertTrue(
            self.librarian.check_password("Original-Librarian-Password-289!")
        )



class LoanListQueryTests(APITestCase):
    def setUp(self):
        self.editorial = Editorial.objects.create(name="Editorial de préstamos")
        self.librarian = User.objects.create_user(
            username="loan-librarian",
            dni=60111222,
            email="loan-librarian@example.com",
            password="test-password",
            rol=User.Rol.LIBRARIAN,
        )
        self.reader = User.objects.create_user(
            username="camila",
            dni=60111223,
            email="camila@example.com",
            password="test-password",
            first_name="Camila",
            last_name="Pérez",
            rol=User.Rol.USER,
        )
        self.client.force_authenticate(user=self.librarian)

    def create_loan(self, title, code, due_at, returned_at=None, user=None):
        book = Book.objects.create(title=title, editorial=self.editorial)
        item = Item.objects.create(book=book, inventory_code=code)
        loaned_at = timezone.now() - timedelta(days=10)
        return Loan.objects.create(
            item=item,
            user=user or self.reader,
            loaned_at=loaned_at,
            due_at=due_at,
            returned_at=returned_at,
        )

    def test_filters_by_user_item_and_status(self):
        now = timezone.now()
        active = self.create_loan(
            "Libro Activo", "INV-ACTIVO", now + timedelta(days=3)
        )
        overdue = self.create_loan(
            "Libro Vencido", "INV-VENCIDO", now - timedelta(days=3)
        )
        returned = self.create_loan(
            "Libro Devuelto",
            "INV-DEVUELTO",
            now - timedelta(days=5),
            returned_at=now - timedelta(days=1),
        )
        due_today_at = timezone.make_aware(
            datetime.combine(timezone.localdate(now), time(23, 59, 59))
        )
        due_today = self.create_loan("Libro para hoy", "INV-HOY", due_today_at)

        response = self.client.get(
            reverse("folium_api:loan-list"),
            {"user": "Camila Pérez", "item": "INV-VENCIDO", "status": "overdue"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["id"] for row in response.data["results"]],
            [overdue.id],
        )
        self.assertEqual(
            response.data["summary"],
            {
                "due_today": 1,
                "due_total": 3,
                "overdue": 1,
            },
        )

        for status_filter, expected_ids in (
            ("active", [due_today.id, active.id]),
            ("overdue", [overdue.id]),
            ("returned", [returned.id]),
        ):
            with self.subTest(status=status_filter):
                response = self.client.get(
                    reverse("folium_api:loan-list"),
                    {"status": status_filter},
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    [row["id"] for row in response.data["results"]],
                    expected_ids,
                )

    def test_remaining_sort_keeps_active_overdue_and_returned_groups(self):
        now = timezone.now()
        active_later = self.create_loan(
            "Activo Lejano", "INV-ACTIVO-2", now + timedelta(days=5)
        )
        overdue_older = self.create_loan(
            "Vencido Antiguo", "INV-VENCIDO-2", now - timedelta(days=8)
        )
        returned = self.create_loan(
            "Ya Devuelto",
            "INV-DEVUELTO-2",
            now - timedelta(days=9),
            returned_at=now - timedelta(days=2),
        )
        active_soon = self.create_loan(
            "Activo Próximo", "INV-ACTIVO-1", now + timedelta(days=1)
        )
        overdue_recent = self.create_loan(
            "Vencido Reciente", "INV-VENCIDO-1", now - timedelta(days=2)
        )

        response = self.client.get(
            reverse("folium_api:loan-list"), {"ordering": "remaining"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["id"] for row in response.data["results"]],
            [
                active_soon.id,
                active_later.id,
                overdue_older.id,
                overdue_recent.id,
                returned.id,
            ],
        )

        descending_response = self.client.get(
            reverse("folium_api:loan-list"), {"ordering": "-remaining"}
        )
        self.assertEqual(descending_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["id"] for row in descending_response.data["results"]],
            [
                active_later.id,
                active_soon.id,
                overdue_recent.id,
                overdue_older.id,
                returned.id,
            ],
        )

    def test_item_ordering_and_page_size_return_drf_pagination(self):
        now = timezone.now()
        second = self.create_loan(
            "Zeta", "INV-ZETA", now + timedelta(days=3)
        )
        first = self.create_loan(
            "Alfa", "INV-ALFA", now + timedelta(days=3)
        )
        third = self.create_loan(
            "Beta", "INV-BETA", now + timedelta(days=3)
        )

        response = self.client.get(
            reverse("folium_api:loan-list"),
            {"ordering": "item", "page": 1, "page_size": 2},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["summary"]["due_total"], 3)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        self.assertEqual(
            [row["id"] for row in response.data["results"]],
            [first.id, third.id],
        )

        next_response = self.client.get(
            reverse("folium_api:loan-list"),
            {"ordering": "item", "page": 2, "page_size": 2},
        )
        self.assertEqual(next_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [row["id"] for row in next_response.data["results"]],
            [second.id],
        )

    def test_page_size_is_capped_at_50(self):
        now = timezone.now()
        for index in range(51):
            self.create_loan(
                f"Libro {index}",
                f"INV-PAGE-{index}",
                now + timedelta(days=3),
            )

        response = self.client.get(
            reverse("folium_api:loan-list"), {"page_size": 100}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 51)
        self.assertEqual(len(response.data["results"]), 50)
        self.assertIsNotNone(response.data["next"])

    def test_invalid_status_or_ordering_returns_validation_error(self):
        for params in ({"status": "unknown"}, {"ordering": "not-allowed"}):
            with self.subTest(params=params):
                response = self.client.get(reverse("folium_api:loan-list"), params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reader_filters_remain_scoped_to_the_authenticated_user(self):
        other_reader = User.objects.create_user(
            username="other-reader",
            dni=60111224,
            email="other-reader@example.com",
            password="test-password",
            rol=User.Rol.USER,
        )
        self.create_loan(
            "Préstamo de Camila",
            "INV-CAMILA",
            timezone.now() + timedelta(days=2),
        )
        other_loan = self.create_loan(
            "Préstamo de otra persona",
            "INV-OTRO",
            timezone.now() + timedelta(days=2),
            user=other_reader,
        )
        self.client.force_authenticate(user=self.reader)

        response = self.client.get(
            reverse("folium_api:loan-list"), {"user": "other-reader"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["summary"]["due_total"], 1)
        self.assertNotIn(
            other_loan.id,
            [row["id"] for row in response.data["results"]],
        )


class ReservationListQueryTests(APITestCase):
    def setUp(self):
        self.editorial = Editorial.objects.create(name="Editorial de reservas")
        self.librarian = User.objects.create_user(
            username="reservation-librarian",
            dni=70111222,
            email="reservation-librarian@example.com",
            password="test-password",
            rol=User.Rol.LIBRARIAN,
        )
        self.reader = User.objects.create_user(
            username="camila-reservation",
            dni=70111223,
            email="camila-reservation@example.com",
            password="test-password",
            first_name="Camila",
            last_name="Pérez",
            rol=User.Rol.USER,
        )
        self.client.force_authenticate(user=self.librarian)

    def create_reservation(self, title, status, expires_at, user=None, isbn=None):
        book = Book.objects.create(
            title=title,
            editorial=self.editorial,
            isbn=isbn,
        )
        return Reservation.objects.create(
            book=book,
            user=user or self.reader,
            status=status,
            expires_at=expires_at,
        )

    def test_filters_by_user_book_and_effective_expired_status(self):
        now = timezone.now()
        expired_reservation = self.create_reservation(
            "El gato negro",
            Reservation.StatusReservation.PENDING,
            now - timedelta(days=1),
            isbn="9780000000001",
        )
        self.create_reservation(
            "Libro pendiente",
            Reservation.StatusReservation.PENDING,
            now + timedelta(days=2),
            isbn="9780000000002",
        )

        response = self.client.get(
            reverse("folium_api:reservation-list"),
            {
                "user": "Camila Pérez",
                "book": "9780000000001",
                "status": "expired",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(
            [reservation["id"] for reservation in response.data],
            [expired_reservation.id],
        )

    def test_status_filters_and_date_order_keep_priority_groups(self):
        now = timezone.now()
        late_pending = self.create_reservation(
            "Pendiente tardía",
            Reservation.StatusReservation.PENDING,
            now + timedelta(days=1),
        )
        early_pending = self.create_reservation(
            "Pendiente temprana",
            Reservation.StatusReservation.PENDING,
            now + timedelta(days=1),
        )
        expired = self.create_reservation(
            "Expirada",
            Reservation.StatusReservation.EXPIRED,
            now - timedelta(days=1),
        )
        completed = self.create_reservation(
            "Completada",
            Reservation.StatusReservation.COMPLETED,
            now + timedelta(days=1),
        )
        cancelled = self.create_reservation(
            "Cancelada",
            Reservation.StatusReservation.CANCELED,
            now + timedelta(days=1),
        )
        Reservation.objects.filter(pk=late_pending.pk).update(
            created_at=now - timedelta(days=2)
        )
        Reservation.objects.filter(pk=early_pending.pk).update(
            created_at=now - timedelta(days=1)
        )

        response = self.client.get(
            reverse("folium_api:reservation-list"),
            {"ordering": "created_at"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [reservation["id"] for reservation in response.data],
            [
                late_pending.id,
                early_pending.id,
                expired.id,
                completed.id,
                cancelled.id,
            ],
        )
        descending_response = self.client.get(
            reverse("folium_api:reservation-list"),
            {"ordering": "-created_at"},
        )
        self.assertEqual(descending_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [reservation["id"] for reservation in descending_response.data],
            [
                early_pending.id,
                late_pending.id,
                expired.id,
                completed.id,
                cancelled.id,
            ],
        )

        for status_filter, expected in (
            ("pending", {late_pending.id, early_pending.id}),
            ("expired", {expired.id}),
            ("completed", {completed.id}),
            ("cancelled", {cancelled.id}),
        ):
            with self.subTest(status=status_filter):
                filtered = self.client.get(
                    reverse("folium_api:reservation-list"),
                    {"status": status_filter},
                )
                self.assertEqual(filtered.status_code, status.HTTP_200_OK)
                self.assertEqual(
                    {reservation["id"] for reservation in filtered.data},
                    expected,
                )

    def test_title_ordering_and_summary_endpoint(self):
        now = timezone.now()
        zeta = self.create_reservation(
            "Zeta",
            Reservation.StatusReservation.PENDING,
            now + timedelta(days=2),
        )
        alfa = self.create_reservation(
            "Alfa",
            Reservation.StatusReservation.PENDING,
            now + timedelta(days=2),
        )
        completed = self.create_reservation(
            "Completada",
            Reservation.StatusReservation.COMPLETED,
            now + timedelta(days=2),
        )
        cancelled = self.create_reservation(
            "Cancelada",
            Reservation.StatusReservation.CANCELED,
            now + timedelta(days=2),
        )
        expired = self.create_reservation(
            "Pendiente vencida",
            Reservation.StatusReservation.PENDING,
            now - timedelta(days=1),
        )

        response = self.client.get(
            reverse("folium_api:reservation-list"), {"ordering": "title"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [reservation["id"] for reservation in response.data],
            [alfa.id, cancelled.id, completed.id, expired.id, zeta.id],
        )

        summary = self.client.get(reverse("folium_api:reservation-summary"))
        self.assertEqual(summary.status_code, status.HTTP_200_OK)
        self.assertEqual(
            summary.data,
            {"pending": 2, "completed": 1, "cancelled": 1},
        )

    def test_invalid_status_or_ordering_returns_validation_error(self):
        for params in ({"status": "unknown"}, {"ordering": "not-allowed"}):
            with self.subTest(params=params):
                response = self.client.get(
                    reverse("folium_api:reservation-list"), params
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reader_list_and_summary_remain_scoped_to_authenticated_user(self):
        other_reader = User.objects.create_user(
            username="other-reservation-reader",
            dni=70111224,
            email="other-reservation-reader@example.com",
            password="test-password",
            rol=User.Rol.USER,
        )
        own_reservation = self.create_reservation(
            "Reserva propia",
            Reservation.StatusReservation.PENDING,
            timezone.now() + timedelta(days=1),
        )
        other_reservation = self.create_reservation(
            "Reserva ajena",
            Reservation.StatusReservation.COMPLETED,
            timezone.now() + timedelta(days=1),
            user=other_reader,
        )
        self.client.force_authenticate(user=self.reader)

        response = self.client.get(reverse("folium_api:reservation-list"))
        summary = self.client.get(reverse("folium_api:reservation-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [reservation["id"] for reservation in response.data],
            [own_reservation.id],
        )
        self.assertNotIn(other_reservation.id, [row["id"] for row in response.data])
        self.assertEqual(
            summary.data,
            {"pending": 1, "completed": 0, "cancelled": 0},
        )


class ReservationCancellationTests(APITestCase):
    def setUp(self):
        from django.utils import timezone
        from datetime import timedelta
        from .models import Reservation

        self.editorial = Editorial.objects.create(name="Editorial Test")
        self.book = Book.objects.create(
            title="Libro Reserva Test",
            isbn="9780000000099",
            editorial=self.editorial,
            publication_year=2024,
        )
        self.item = Item.objects.create(
            book=self.book,
            inventory_code="RES-001",
            status=Item.Status.RESERVED,
        )
        self.reader_1 = User.objects.create_user(
            username="reader1",
            dni=11111111,
            email="reader1@example.com",
            password="test-password",
            rol=User.Rol.USER,
        )
        self.reader_2 = User.objects.create_user(
            username="reader2",
            dni=22222222,
            email="reader2@example.com",
            password="test-password",
            rol=User.Rol.USER,
        )
        self.librarian = User.objects.create_user(
            username="librarian-res",
            dni=33333333,
            email="librarian-res@example.com",
            password="test-password",
            rol=User.Rol.LIBRARIAN,
        )
        self.reservation = Reservation.objects.create(
            book=self.book,
            item=self.item,
            user=self.reader_1,
            status=Reservation.StatusReservation.PENDING,
            expires_at=timezone.now() + timedelta(days=2),
        )

    def test_creating_pending_reservation_reserves_one_available_item(self):
        self.reservation.delete()
        self.item.status = Item.Status.AVAILABLE
        self.item.save(update_fields=["status"])
        second_item = Item.objects.create(
            book=self.book,
            inventory_code="RES-002",
            status=Item.Status.AVAILABLE,
        )
        self.client.force_authenticate(user=self.reader_2)

        response = self.client.post(
            reverse("folium_api:reservation-list"),
            {
                "book": self.book.id,
                "expires_at": (timezone.now() + timedelta(days=2)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reservation = Reservation.objects.get(pk=response.data["id"])
        self.item.refresh_from_db()
        second_item.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.StatusReservation.PENDING)
        self.assertEqual(reservation.item_id, self.item.id)
        self.assertEqual(self.item.status, Item.Status.RESERVED)
        self.assertEqual(second_item.status, Item.Status.AVAILABLE)

    def test_pending_reservation_without_available_item_fails_validation(self):
        self.client.force_authenticate(user=self.reader_2)

        response = self.client.post(
            reverse("folium_api:reservation-list"),
            {
                "book": self.book.id,
                "expires_at": (timezone.now() + timedelta(days=2)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_reserved_item_can_be_loaned_to_its_reserving_user(self):
        self.client.force_authenticate(user=self.librarian)

        response = self.client.post(
            reverse("folium_api:loan-list"),
            {"item": self.item.id, "user": self.reader_1.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.reservation.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(
            self.reservation.status,
            Reservation.StatusReservation.COMPLETED,
        )
        self.assertEqual(self.item.status, Item.Status.LOANED)

    def test_reserved_item_cannot_be_loaned_to_another_user(self):
        self.client.force_authenticate(user=self.librarian)

        response = self.client.post(
            reverse("folium_api:loan-list"),
            {"item": self.item.id, "user": self.reader_2.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Item.Status.RESERVED)

    def test_reader_can_cancel_own_reservation(self):
        self.client.force_authenticate(user=self.reader_1)
        url = reverse("folium_api:reservation-cancel", args=[self.reservation.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reservation.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.reservation.status, "CANCELLED")
        self.assertIsNone(self.reservation.item_id)
        self.assertEqual(self.item.status, Item.Status.AVAILABLE)

    def test_updating_pending_reservation_releases_its_item(self):
        self.client.force_authenticate(user=self.reader_1)
        response = self.client.patch(
            reverse("folium_api:reservation-detail", args=[self.reservation.id]),
            {"status": Reservation.StatusReservation.CANCELED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reservation.refresh_from_db()
        self.item.refresh_from_db()
        self.assertIsNone(self.reservation.item_id)
        self.assertEqual(self.item.status, Item.Status.AVAILABLE)

    def test_reader_cannot_cancel_other_reader_reservation(self):
        self.client.force_authenticate(user=self.reader_2)
        url = reverse("folium_api:reservation-cancel", args=[self.reservation.id])
        response = self.client.post(url)
        # get_queryset filtra y devuelve 404 al no pertenecerle
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    def test_librarian_can_cancel_any_reservation(self):
        self.client.force_authenticate(user=self.librarian)
        url = reverse("folium_api:reservation-cancel", args=[self.reservation.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, "CANCELLED")


class BillingMercadoPagoTests(APITestCase):
    def test_billing_plans_list(self):
        url = reverse("folium_api:billing-plans")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("plans", response.data)
        self.assertIn("gateway", response.data)
        plan_codes = [p["code"] for p in response.data["plans"]]
        self.assertIn("BASIC", plan_codes)
        self.assertIn("PRO", plan_codes)
        self.assertIn("PREMIUM", plan_codes)

    def test_checkout_preference_validation_error_on_invalid_plan(self):
        url = reverse("folium_api:billing-checkout")
        payload = {
            "plan_code": "INVALID_PLAN",
            "billing_cycle": "MONTHLY",
            "organization_name": "Biblioteca San Martín",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plan_code", response.data)

    def test_checkout_preference_valid_payload(self):
        url = reverse("folium_api:billing-checkout")
        payload = {
            "plan_code": "BASIC",
            "billing_cycle": "MONTHLY",
            "organization_name": "Biblioteca Central",
            "payer_email": "admin@biblioteca.org",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertIn("checkout", response.data)
        self.assertIn("preference_id", response.data["checkout"])
        self.assertIn("init_point", response.data["checkout"])

    def test_checkout_creates_pending_subscription(self):
        url = reverse("folium_api:billing-checkout")
        response = self.client.post(
            url,
            {
                "plan_code": "PRO",
                "billing_cycle": "ANNUAL",
                "organization_name": "Biblioteca del Sur",
                "tax_id": "20123456789",
                "payer_email": "sur@biblioteca.org",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        external_reference = response.data["checkout"]["external_reference"]
        subscription = LibrarySubscription.objects.get(
            external_reference=external_reference
        )
        self.assertEqual(subscription.status, LibrarySubscription.Status.PENDING)
        self.assertEqual(subscription.plan.code, "PRO")
        self.assertEqual(subscription.billing_cycle, "ANNUAL")
        self.assertEqual(
            subscription.mp_preference_id,
            response.data["checkout"]["preference_id"],
        )

    @patch(
        "folium_api.mercadopago_service.MercadoPagoService.fetch_payment_details",
        return_value={
            "id": "PAYMENT-123",
            "external_reference": "FOLIUM-PRO-MONTHLY-U0-TEST",
            "status": "approved",
            "status_detail": "accredited",
            "transaction_amount": 455000,
            "currency_id": "ARS",
            "payment_method_id": "visa",
            "payment_type_id": "credit_card",
            "payer": {"email": "pagador@biblioteca.org"},
        },
    )
    def test_webhook_persists_payment_and_activates_subscription(self, _fetch):
        plan = SubscriptionPlan.objects.create(
            code="PRO",
            name="Folium Integral",
            monthly_price="455000.00",
            annual_monthly_equivalent="379100.00",
        )
        subscription = LibrarySubscription.objects.create(
            plan=plan,
            organization_name="Biblioteca del Sur",
            payer_email="pagador@biblioteca.org",
            external_reference="FOLIUM-PRO-MONTHLY-U0-TEST",
        )
        url = reverse("folium_api:billing-mp-webhook")

        response = self.client.post(
            url,
            {"type": "payment", "data": {"id": "PAYMENT-123"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, LibrarySubscription.Status.ACTIVE)
        self.assertIsNotNone(subscription.current_period_start)
        self.assertIsNotNone(subscription.current_period_end)
        self.assertEqual(
            PaymentTransaction.objects.filter(mp_payment_id="PAYMENT-123").count(),
            1,
        )
        payment = PaymentTransaction.objects.get(mp_payment_id="PAYMENT-123")
        self.assertEqual(payment.subscription, subscription)
        self.assertEqual(payment.status, "approved")
        self.assertTrue(WebhookEventLog.objects.filter(processed=True).exists())

        response = self.client.post(
            url,
            {"type": "payment", "data": {"id": "PAYMENT-123"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            PaymentTransaction.objects.filter(mp_payment_id="PAYMENT-123").count(),
            1,
        )


class UserPrivilegeEscalationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="priv-admin",
            dni=91000001,
            email="priv-admin@example.com",
            password="StrongAdminPassword-123!",
            rol=User.Rol.ADMIN,
        )
        self.librarian = User.objects.create_user(
            username="priv-librarian",
            dni=91000002,
            email="priv-librarian@example.com",
            password="StrongLibrarianPassword-123!",
            rol=User.Rol.LIBRARIAN,
        )
        self.reader = User.objects.create_user(
            username="priv-reader",
            dni=91000003,
            email="priv-reader@example.com",
            password="StrongReaderPassword-123!",
            rol=User.Rol.USER,
        )

    def test_librarian_cannot_create_or_promote_to_admin(self):
        self.client.force_authenticate(user=self.librarian)
        create_res = self.client.post(
            "/api/v1/user/",
            {
                "username": "new-admin",
                "dni": 91000004,
                "email": "new-admin@example.com",
                "rol": User.Rol.ADMIN,
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_400_BAD_REQUEST)

        promote_res = self.client.patch(
            f"/api/v1/user/{self.reader.id}/",
            {"rol": User.Rol.ADMIN},
            format="json",
        )
        self.assertEqual(promote_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.rol, User.Rol.USER)

    def test_librarian_cannot_view_or_modify_admin_or_other_user_password(self):
        self.client.force_authenticate(user=self.librarian)

        list_res = self.client.get("/api/v1/user/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        returned_ids = [u["id"] for u in list_res.data]
        self.assertNotIn(self.admin.id, returned_ids)
        self.assertIn(self.reader.id, returned_ids)

        by_dni_res = self.client.get(f"/api/v1/user/by-dni/{self.admin.dni}/")
        self.assertEqual(by_dni_res.status_code, status.HTTP_404_NOT_FOUND)

        patch_admin = self.client.patch(
            f"/api/v1/user/{self.admin.id}/",
            {"password": "HackedPassword-123!"},
            format="json",
        )
        self.assertEqual(patch_admin.status_code, status.HTTP_404_NOT_FOUND)

        patch_reader_pw = self.client.patch(
            f"/api/v1/user/{self.reader.id}/",
            {"password": "OtherPassword-123!"},
            format="json",
        )
        self.assertEqual(patch_reader_pw.status_code, status.HTTP_400_BAD_REQUEST)
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password("StrongReaderPassword-123!"))

        patch_reader_active = self.client.patch(
            f"/api/v1/user/{self.reader.id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(patch_reader_active.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_manage_roles_and_passwords(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/v1/user/{self.librarian.id}/",
            {"rol": User.Rol.ADMIN, "password": "RotatedAdminPassword-123!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.librarian.refresh_from_db()
        self.assertEqual(self.librarian.rol, User.Rol.ADMIN)
        self.assertTrue(self.librarian.check_password("RotatedAdminPassword-123!"))


class PasswordPolicyValidationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="pw-admin",
            dni=91100001,
            email="pw-admin@example.com",
            password="StrongAdminPassword-123!",
            rol=User.Rol.ADMIN,
        )

    def test_register_rejects_numeric_common_and_similar_passwords(self):
        for bad_pw in ("12345678", "password", "lectornuevo1"):
            with self.subTest(password=bad_pw):
                res = self.client.post(
                    reverse("folium_api:reader-register"),
                    {
                        "username": "lectornuevo1",
                        "dni": 91100002,
                        "first_name": "Lector",
                        "last_name": "Nuevo",
                        "email": "lectornuevo1@example.com",
                        "password": bad_pw,
                    },
                    format="json",
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("password", res.data)

    def test_user_create_and_update_enforce_password_validators(self):
        self.client.force_authenticate(user=self.admin)
        create_res = self.client.post(
            "/api/v1/user/",
            {
                "username": "usuariodeprueba",
                "dni": 91100003,
                "first_name": "Maria",
                "last_name": "Lopez",
                "email": "maria.lopez@example.com",
                "password": "usuariodeprueba",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", create_res.data)

        valid_res = self.client.post(
            "/api/v1/user/",
            {
                "username": "usuariodeprueba",
                "dni": 91100003,
                "first_name": "Maria",
                "last_name": "Lopez",
                "email": "maria.lopez@example.com",
                "password": "Complex-User-Secret-2026!",
            },
            format="json",
        )
        self.assertEqual(valid_res.status_code, status.HTTP_201_CREATED)
        user_id = valid_res.data["id"]

        patch_res = self.client.patch(
            f"/api/v1/user/{user_id}/",
            {"password": "12345678"},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", patch_res.data)


class SeedDataSafetyTests(APITestCase):
    def test_seed_data_aborts_when_debug_is_false_without_force(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.test import override_settings

        with override_settings(DEBUG=False):
            with self.assertRaises(CommandError):
                call_command("seed_data")

    def test_seed_data_without_flush_preserves_existing_loans_and_reservations(self):
        import io
        import tempfile
        from django.core.management import call_command
        from django.test import override_settings

        editorial = Editorial.objects.create(name="Editorial Persistente")
        book = Book.objects.create(title="Libro Existente", editorial=editorial)
        item = Item.objects.create(
            book=book,
            inventory_code="KEEP-001",
            status=Item.Status.LOANED,
        )
        reader = User.objects.create_user(
            username="keep-reader",
            dni=91200001,
            email="keep-reader@example.com",
            password="StrongKeepPassword-123!",
        )
        loan = Loan.objects.create(
            item=item,
            user=reader,
            loaned_at=timezone.now() - timedelta(days=2),
            due_at=timezone.now() + timedelta(days=12),
        )
        reservation = Reservation.objects.create(
            book=book,
            user=reader,
            status=Reservation.StatusReservation.PENDING,
            expires_at=timezone.now() + timedelta(days=3),
        )

        with tempfile.TemporaryDirectory() as tmp_media:
            with override_settings(DEBUG=True, MEDIA_ROOT=tmp_media):
                call_command("seed_data", stdout=io.StringIO(), stderr=io.StringIO())

        self.assertTrue(Loan.objects.filter(pk=loan.pk).exists())
        self.assertTrue(Reservation.objects.filter(pk=reservation.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.status, Item.Status.LOANED)


class AuthExceptionHandlerTests(APITestCase):
    def setUp(self):
        self.inactive_user = User.objects.create_user(
            username="inactive-reader",
            dni=91300001,
            email="inactive@example.com",
            password="StrongPassword-123!",
            is_active=False,
        )

    def test_401_responses_are_uniform_and_logged(self):
        from folium_api.exceptions import UNIFORM_AUTH_ERROR_DETAIL

        with self.assertLogs("folium_api.auth", level="WARNING") as unauth_logs:
            unauth_res = self.client.get("/api/v1/user/")
        self.assertEqual(unauth_res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unauth_res.data, {"detail": UNIFORM_AUTH_ERROR_DETAIL})
        self.assertTrue(unauth_logs.output)

        with self.assertLogs("folium_api.auth", level="WARNING") as bad_creds_logs:
            bad_creds_res = self.client.post(
                reverse("token_obtain_pair"),
                {"username": "nonexistent", "password": "wrong"},
                format="json",
            )
        self.assertEqual(bad_creds_res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(bad_creds_res.data, {"detail": UNIFORM_AUTH_ERROR_DETAIL})
        self.assertTrue(bad_creds_logs.output)

        with self.assertLogs("folium_api.auth", level="WARNING") as inactive_logs:
            inactive_res = self.client.post(
                reverse("token_obtain_pair"),
                {"username": "inactive-reader", "password": "StrongPassword-123!"},
                format="json",
            )
        self.assertEqual(inactive_res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(inactive_res.data, {"detail": UNIFORM_AUTH_ERROR_DETAIL})
        self.assertTrue(inactive_logs.output)

        with self.assertLogs("folium_api.auth", level="WARNING") as jwt_logs:
            bad_jwt_res = self.client.get(
                "/api/v1/user/",
                HTTP_AUTHORIZATION="Bearer not.a.valid.jwt",
            )
        self.assertEqual(bad_jwt_res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(bad_jwt_res.data, {"detail": UNIFORM_AUTH_ERROR_DETAIL})
        self.assertTrue(jwt_logs.output)


class TrailingSlashPostRoutesTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="slash-reader",
            dni=91400001,
            email="slash-reader@example.com",
            password="StrongPassword-123!",
        )

    def test_token_refresh_and_webhook_accept_post_without_trailing_slash(self):
        token_res = self.client.post(
            "/api/v1/token",
            {"username": "slash-reader", "password": "StrongPassword-123!"},
            format="json",
        )
        self.assertEqual(token_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", token_res.data)
        self.assertIn("refresh", token_res.data)

        refresh_res = self.client.post(
            "/api/v1/token/refresh",
            {"refresh": token_res.data["refresh"]},
            format="json",
        )
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_res.data)

        webhook_res = self.client.post(
            "/api/v1/billing/webhook/mercadopago",
            {"type": "payment", "data": {"id": "999999"}},
            format="json",
        )
        self.assertNotEqual(webhook_res.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(webhook_res.status_code, status.HTTP_200_OK)


class FavoriteBehaviorTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fav-reader",
            dni=91500001,
            email="fav-reader@example.com",
            password="StrongPassword-123!",
        )
        self.editorial = Editorial.objects.create(name="Fav Editorial")
        self.book = Book.objects.create(title="Libro Favorito", editorial=self.editorial)
        self.deleted_book = Book.objects.create(
            title="Libro Eliminado",
            editorial=self.editorial,
            deleted_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.user)

    def test_duplicate_favorite_returns_200_and_soft_deleted_book_returns_400(self):
        first = self.client.post("/api/v1/favorites/", {"book": self.book.id}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post("/api/v1/favorites/", {"book": self.book.id}, format="json")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(
            User.favorites.through.objects.filter(user=self.user, book=self.book).count(),
            1,
        )

        deleted_res = self.client.post(
            "/api/v1/favorites/",
            {"book": self.deleted_book.id},
            format="json",
        )
        self.assertEqual(deleted_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("book", deleted_res.data)


class BookOptionsHttpHandlerTests(APITestCase):
    def test_http_options_and_book_options_action_both_work(self):
        options_meta = self.client.options("/api/v1/book/")
        self.assertEqual(options_meta.status_code, status.HTTP_200_OK)

        book_options_res = self.client.get(reverse("folium_api:book-options"))
        self.assertEqual(book_options_res.status_code, status.HTTP_200_OK)


class ItemStateMachineTests(APITestCase):
    def setUp(self):
        self.librarian = User.objects.create_user(
            username="fsm-librarian",
            dni=91600001,
            email="fsm-librarian@example.com",
            password="StrongPassword-123!",
            rol=User.Rol.LIBRARIAN,
        )
        self.reader = User.objects.create_user(
            username="fsm-reader",
            dni=91600002,
            email="fsm-reader@example.com",
            password="StrongPassword-123!",
            rol=User.Rol.USER,
        )
        self.editorial = Editorial.objects.create(name="FSM Editorial")
        self.book = Book.objects.create(title="FSM Libro", editorial=self.editorial)
        self.deleted_book = Book.objects.create(
            title="FSM Eliminado",
            editorial=self.editorial,
            deleted_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.librarian)

    def test_item_fsm_blocks_invalid_transitions_and_allows_mark_reviewed(self):
        deleted_book_res = self.client.post(
            "/api/v1/items/",
            {"book": self.deleted_book.id, "inventory_code": "FSM-DEL-1"},
            format="json",
        )
        self.assertEqual(deleted_book_res.status_code, status.HTTP_400_BAD_REQUEST)

        for blocked_status in (Item.Status.LOANED, Item.Status.RESERVED):
            create_blocked = self.client.post(
                "/api/v1/items/",
                {
                    "book": self.book.id,
                    "inventory_code": f"FSM-{blocked_status}",
                    "status": blocked_status,
                },
                format="json",
            )
            self.assertEqual(create_blocked.status_code, status.HTTP_400_BAD_REQUEST)

        created_res = self.client.post(
            "/api/v1/items/",
            {"book": self.book.id, "inventory_code": "FSM-OK-1", "location": "A1"},
            format="json",
        )
        self.assertEqual(created_res.status_code, status.HTTP_201_CREATED)
        item_id = created_res.data["id"]

        to_damaged = self.client.patch(
            f"/api/v1/items/{item_id}/",
            {"status": Item.Status.DAMAGED},
            format="json",
        )
        self.assertEqual(to_damaged.status_code, status.HTTP_200_OK)

        direct_rehabilitate = self.client.patch(
            f"/api/v1/items/{item_id}/",
            {"status": Item.Status.AVAILABLE},
            format="json",
        )
        self.assertEqual(direct_rehabilitate.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(user=self.reader)
        reader_review = self.client.post(f"/api/v1/items/{item_id}/mark-reviewed/")
        self.assertEqual(reader_review.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.librarian)
        lib_review = self.client.post(f"/api/v1/items/{item_id}/mark-reviewed/")
        self.assertEqual(lib_review.status_code, status.HTTP_200_OK)
        self.assertEqual(lib_review.data["status"], Item.Status.AVAILABLE)

        repeat_review = self.client.post(f"/api/v1/items/{item_id}/mark-reviewed/")
        self.assertEqual(repeat_review.status_code, status.HTTP_400_BAD_REQUEST)

    def test_item_blocks_status_change_and_delete_when_loaned_or_reserved(self):
        loaned_item = Item.objects.create(
            book=self.book,
            inventory_code="FSM-LOAN-1",
            status=Item.Status.LOANED,
            location="Estante 1",
        )
        loan = Loan.objects.create(
            item=loaned_item,
            user=self.reader,
            loaned_at=timezone.now() - timedelta(days=1),
            due_at=timezone.now() + timedelta(days=7),
        )

        # Updating location without changing status stays allowed
        patch_location = self.client.patch(
            f"/api/v1/items/{loaned_item.id}/",
            {"status": Item.Status.LOANED, "location": "Estante 2"},
            format="json",
        )
        self.assertEqual(patch_location.status_code, status.HTTP_200_OK)

        patch_status = self.client.patch(
            f"/api/v1/items/{loaned_item.id}/",
            {"status": Item.Status.DAMAGED},
            format="json",
        )
        self.assertEqual(patch_status.status_code, status.HTTP_400_BAD_REQUEST)

        del_loaned = self.client.delete(f"/api/v1/items/{loaned_item.id}/")
        self.assertEqual(del_loaned.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Loan.objects.filter(pk=loan.pk).exists())

        reserved_item = Item.objects.create(
            book=self.book,
            inventory_code="FSM-RES-1",
            status=Item.Status.RESERVED,
        )
        reservation = Reservation.objects.create(
            book=self.book,
            item=reserved_item,
            user=self.reader,
            status=Reservation.StatusReservation.PENDING,
            expires_at=timezone.now() + timedelta(days=2),
        )

        patch_reserved = self.client.patch(
            f"/api/v1/items/{reserved_item.id}/",
            {"status": Item.Status.DAMAGED},
            format="json",
        )
        self.assertEqual(patch_reserved.status_code, status.HTTP_400_BAD_REQUEST)

        del_reserved = self.client.delete(f"/api/v1/items/{reserved_item.id}/")
        self.assertEqual(del_reserved.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Reservation.objects.filter(pk=reservation.pk).exists())

        free_item = Item.objects.create(
            book=self.book,
            inventory_code="FSM-FREE-1",
            status=Item.Status.AVAILABLE,
        )
        del_free = self.client.delete(f"/api/v1/items/{free_item.id}/")
        self.assertEqual(del_free.status_code, status.HTTP_204_NO_CONTENT)


class IntegerQueryParamValidationTests(APITestCase):
    def setUp(self):
        self.librarian = User.objects.create_user(
            username="pgint-librarian",
            dni=91700001,
            email="pgint-librarian@example.com",
            password="StrongPassword-123!",
            rol=User.Rol.LIBRARIAN,
        )
        self.editorial = Editorial.objects.create(name="PgInt Editorial")
        self.book = Book.objects.create(
            title="PgInt Libro",
            isbn="9788420412146",
            publication_year=2020,
            editorial=self.editorial,
        )
        self.item = Item.objects.create(
            book=self.book,
            inventory_code="9788420412146",
            status=Item.Status.AVAILABLE,
        )

    def test_invalid_and_overflow_numeric_filters_return_400_not_500(self):
        for bad_year in ("abc", "0", "-10", "99999999999999"):
            res = self.client.get(f"/api/v1/book/?year={bad_year}")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        self.client.force_authenticate(user=self.librarian)
        for bad_book in ("abc", "0", "99999999999999"):
            items_res = self.client.get(f"/api/v1/items/?book={bad_book}")
            self.assertEqual(items_res.status_code, status.HTTP_400_BAD_REQUEST)

            reviews_res = self.client.get(f"/api/v1/reviews/?book={bad_book}")
            self.assertEqual(reviews_res.status_code, status.HTTP_400_BAD_REQUEST)

        for bad_dni in ("abc", "0", "99999999999999"):
            users_res = self.client.get(f"/api/v1/user/?dni={bad_dni}")
            self.assertEqual(users_res.status_code, status.HTTP_400_BAD_REQUEST)

        by_dni_overflow = self.client.get("/api/v1/user/by-dni/99999999999999/")
        self.assertEqual(by_dni_overflow.status_code, status.HTTP_400_BAD_REQUEST)

        # Mixed text/ID filters ignore out-of-range numeric IDs and still search text fields
        loan_item_search = self.client.get("/api/v1/loan/?item=9788420412146")
        self.assertEqual(loan_item_search.status_code, status.HTTP_200_OK)

        loan_user_search = self.client.get("/api/v1/loan/?user=99999999999999")
        self.assertEqual(loan_user_search.status_code, status.HTTP_200_OK)

        res_user_search = self.client.get("/api/v1/reservations/?user=99999999999999")
        self.assertEqual(res_user_search.status_code, status.HTTP_200_OK)

        res_book_search = self.client.get("/api/v1/reservations/?book=9788420412146")
        self.assertEqual(res_book_search.status_code, status.HTTP_200_OK)


class LoanConcurrencyAndIntegrityTests(APITestCase):
    def setUp(self):
        self.librarian = User.objects.create_user(
            username="loan-lock-lib",
            dni=91800001,
            email="loan-lock-lib@example.com",
            password="StrongPassword-123!",
            rol=User.Rol.LIBRARIAN,
        )
        self.reader_1 = User.objects.create_user(
            username="loan-lock-r1",
            dni=91800002,
            email="loan-lock-r1@example.com",
            password="StrongPassword-123!",
        )
        self.reader_2 = User.objects.create_user(
            username="loan-lock-r2",
            dni=91800003,
            email="loan-lock-r2@example.com",
            password="StrongPassword-123!",
        )
        self.editorial = Editorial.objects.create(name="LoanLock Editorial")
        self.book = Book.objects.create(title="LoanLock Libro", editorial=self.editorial)
        self.item = Item.objects.create(
            book=self.book,
            inventory_code="LOCK-001",
            status=Item.Status.AVAILABLE,
        )
        self.client.force_authenticate(user=self.librarian)

    def test_db_partial_unique_constraint_blocks_two_active_loans_same_item(self):
        from django.db import IntegrityError, transaction

        now = timezone.now()
        first = Loan.objects.create(
            item=self.item,
            user=self.reader_1,
            loaned_at=now - timedelta(days=2),
            due_at=now + timedelta(days=5),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Loan.objects.create(
                    item=self.item,
                    user=self.reader_2,
                    loaned_at=now,
                    due_at=now + timedelta(days=7),
                )

        first.returned_at = now - timedelta(hours=1)
        first.save(update_fields=["returned_at"])

        second = Loan.objects.create(
            item=self.item,
            user=self.reader_2,
            loaned_at=now,
            due_at=now + timedelta(days=7),
        )
        self.assertIsNotNone(second.pk)

    def test_serializer_rechecks_item_under_lock_before_creating_loan(self):
        from rest_framework.exceptions import ValidationError as DRFValidationError
        from folium_api.serializers import LoanWriteSerializer

        serializer = LoanWriteSerializer(
            data={"item": self.item.id, "user": self.reader_2.id}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        # Simulate concurrent loan committed right after validation passed
        now = timezone.now()
        Loan.objects.create(
            item=self.item,
            user=self.reader_1,
            loaned_at=now,
            due_at=now + timedelta(days=10),
        )
        self.item.status = Item.Status.LOANED
        self.item.save(update_fields=["status"])

        with self.assertRaises(DRFValidationError):
            serializer.save()

    def test_cannot_reopen_returned_loan_or_overwrite_damaged_item_status(self):
        create_res = self.client.post(
            "/api/v1/loan/",
            {"item": self.item.id, "user": self.reader_1.id},
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        loan_id = create_res.data["id"]

        # Simulate item marked damaged before closing loan record
        self.item.status = Item.Status.DAMAGED
        self.item.save(update_fields=["status"])

        return_res = self.client.patch(
            f"/api/v1/loan/{loan_id}/",
            {"returned_at": timezone.now().isoformat()},
            format="json",
        )
        self.assertEqual(return_res.status_code, status.HTTP_200_OK)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, Item.Status.DAMAGED)

        reopen_res = self.client.patch(
            f"/api/v1/loan/{loan_id}/",
            {"returned_at": None},
            format="json",
        )
        self.assertEqual(reopen_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("returned_at", reopen_res.data)
