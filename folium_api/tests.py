from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken
from .models import Author, Book, Editorial, Review, Item

User = get_user_model()


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
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

    def test_items_and_loans_stay_private(self):
        response_items = self.client.get(reverse("folium_api:item-list"))
        self.assertEqual(response_items.status_code, status.HTTP_403_FORBIDDEN)
        response_loans = self.client.get(reverse("folium_api:loan-list"))
        self.assertEqual(response_loans.status_code, status.HTTP_403_FORBIDDEN)

