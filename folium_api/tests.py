from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

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
