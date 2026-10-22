from django.views import View
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView
import random
from django.db.models import Avg, Count, Q, F
from .models import *
from .serializers import *

# Create your views here.

# Usen clases para declarar las views. Un ejemplo hecho con la IA:

'''
class ContactView(View):

    # Handles HTTP GET requests (e.g., loading the page)
    def get(self, request):
        return HttpResponse("This is the contact page (GET request).")

    # Handles HTTP POST requests (e.g., submitting a form)
    def post(self, request):
        name = request.POST.get('name', 'Guest')
        return HttpResponse(f"Thank you for your submission, {name}! (POST request).")
'''

# ==========================================
# PERMISOS PERSONALIZADOS
# ==========================================

class FoliumTokenObtainPairView(TokenObtainPairView):
        serializer_class = FoliumTokenObtainPairSerializer


class IsLibrarian(permissions.BasePermission):
        """
        Permiso que autoriza únicamente a usuarios autenticados 
        cuyo rol sea Bibliotecario (LIBRARIAN) o Administrador (ADMIN).
        """
        def has_permission(self, request, view):
        # 1. Primero verifica que el usuario haya iniciado sesión
                if not (request.user and request.user.is_authenticated):
                        return False

        # 2. Verifica si el rol es LIBRARIAN o ADMIN (o superusuario)
                return (
                        request.user.rol in [User.Rol.LIBRARIAN, User.Rol.ADMIN] 
                        or request.user.is_staff 
                        or request.user.is_superuser
                )


class IsLibrarianOrReadOnly(permissions.BasePermission):
        """
        Permiso que permite lectura (GET, HEAD, OPTIONS) a cualquier usuario autenticado
        (incluyendo lectores), pero restringe la creación, edición y eliminación
        exclusivamente a Bibliotecarios (LIBRARIAN) o Administradores (ADMIN).
        """
        def has_permission(self, request, view):
                # 1. Verifica que el usuario haya iniciado sesión
                if not (request.user and request.user.is_authenticated):
                        return False

                # 2. Si es una acción de solo lectura (catálogo), cualquier usuario autenticado puede acceder
                if request.method in permissions.SAFE_METHODS:
                        return True

                # 3. Acciones de escritura sólo permitidas para LIBRARIAN o ADMIN
                return (
                        request.user.rol in [User.Rol.LIBRARIAN, User.Rol.ADMIN]
                        or request.user.is_staff
                        or request.user.is_superuser
                )


# ==========================================
# VIEWSETS
# ==========================================

class ItemViewSet(viewsets.ModelViewSet):
        """
        Controlador para que el bibliotecario gestione el inventario 
        de ejemplares físicos (copias de los libros).
        """
        queryset = Item.objects.all()
        serializer_class = ItemSerializer
        permission_classes = [IsLibrarianOrReadOnly]


class LoanViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar los préstamos.
        - Bibliotecarios/Admin: gestión completa de todos los préstamos.
        - Lectores: solo lectura de sus propios préstamos.
        """
        serializer_class = LoanWriteSerializer
        permission_classes = [IsLibrarianOrReadOnly]

        def get_queryset(self):
                user = self.request.user
                # Bibliotecarios y administradores pueden ver todos los préstamos
                if user.is_authenticated and (
                        user.rol in [User.Rol.LIBRARIAN, User.Rol.ADMIN]
                        or user.is_staff
                        or user.is_superuser
                ):
                        return Loan.objects.all()
                # Lectores únicamente pueden ver sus propios préstamos
                if user.is_authenticated:
                        return Loan.objects.filter(user=user)
                return Loan.objects.none()

        def get_serializer_class(self):
                if self.action in ['list', 'retrieve']:
                        return LoanReadSerializer
                return LoanWriteSerializer


class BookViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar los libros (catálogo).
        Permite lectura a lectores y gestión completa al bibliotecario.
        """
        queryset = Book.objects.all()
        serializer_class = BookWriteSerializer
        permission_classes = [IsLibrarianOrReadOnly]

        def get_serializer_class(self):
                if self.action == 'list':
                        return BookListSerializer
                elif self.action == 'retrieve':
                        return BookDetailSerializer
                return BookWriteSerializer

        @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='random')
        def random_book(self, request, *args, **kwargs):
                """
                Endpoint público de atajo para obtener un libro al azar dentro de /book/random/.
                """
                return RandomBookView.as_view()(request._request, *args, **kwargs)

        @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='recommendation')
        def recommendation(self, request, *args, **kwargs):
                """
                Endpoint público de atajo para obtener los 10 mejores libros dentro de /book/recommendation/.
                """
                return BookRecommendationView.as_view()(request._request, *args, **kwargs)

        @action(detail=False, methods=['get'], permission_classes=[permissions.AllowAny], url_path='recommendations')
        def recommendations(self, request, *args, **kwargs):
                """
                Alias en plural para recomendaciones.
                """
                return BookRecommendationView.as_view()(request._request, *args, **kwargs)



class AuthorViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar autores.
        Permite lectura a lectores y gestión completa al bibliotecario.
        """
        queryset = Author.objects.all()
        serializer_class = AuthorSerializer
        permission_classes = [IsLibrarianOrReadOnly]


class GenreViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar géneros.
        Permite lectura a lectores y gestión completa al bibliotecario.
        """
        queryset = Genre.objects.all()
        serializer_class = GenreSerializer
        permission_classes = [IsLibrarianOrReadOnly]

class FavoriteViewSet(viewsets.ModelViewSet):
        """
        Controlador para que los usuarios gestionen sus libros favoritos.
        """
        serializer_class = FavoriteSerializer
        permission_classes = [permissions.IsAuthenticated]
        http_method_names = ['get', 'post', 'delete', 'head', 'options']

        def get_queryset(self):
                # Filtra por el usuario logueado y optimiza la carga de relaciones
                return User.favorites.through.objects.filter(
                        user=self.request.user
                ).select_related('user', 'book')

        def perform_create(self, serializer):
                # Asocia el favorito a la persona que mandó el token
                serializer.save(user=self.request.user)

# ==========================================
# VISTAS DEL LECTOR
# ==========================================

class ReaderRegistrationView(generics.CreateAPIView):
        """
        Controlador público para el autoregistro de lectores.
        """
        queryset = User.objects.all()
        serializer_class = UserSerializer
        permission_classes = [permissions.AllowAny]

        def perform_create(self, serializer):
        # Asignamos explícitamente el rol USER al nuevo registrado
                serializer.save(rol=User.Rol.USER)


class UserProfileView(generics.RetrieveUpdateAPIView):
        """
        Permite al usuario autenticado consultar (GET) y actualizar (PATCH/PUT)
        sus datos de perfil personal.
        """
        serializer_class = UserProfileSerializer
        permission_classes = [permissions.IsAuthenticated]

        def get_object(self):
                return self.request.user


class ReservationViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar las reservas.
        - Bibliotecarios/Admin: visualización y gestión de todas las reservas.
        - Lectores: gestión únicamente de sus propias reservas.
        """
        serializer_class = ReservationSerializer
        permission_classes = [permissions.IsAuthenticated]

        def get_queryset(self):
                user = self.request.user
                # Bibliotecarios y administradores pueden ver y gestionar todas las reservas
                if user.is_authenticated and (
                        user.rol in [User.Rol.LIBRARIAN, User.Rol.ADMIN]
                        or user.is_staff
                        or user.is_superuser
                ):
                        return Reservation.objects.all()
                # Un lector solo ve sus propias reservas
                if user.is_authenticated:
                        return Reservation.objects.filter(user=user)
                return Reservation.objects.none()

        def perform_create(self, serializer):
                # Asigna automáticamente el usuario que hace la solicitud
                serializer.save(user=self.request.user)


class ReviewViewSet(viewsets.ModelViewSet):
        """
        Controlador para que los lectores gestionen y consulten reseñas,
        y para que los bibliotecarios moderen (eliminen) comentarios ofensivos.
        - Filtrado por ?book=<id>: lista todas las reseñas activas de ese libro.
        - Sin filtro: lista únicamente las reseñas del usuario autenticado ("Mis reseñas").
        - Modificaciones: solo permitidas al autor de la reseña.
        - Eliminaciones: permitidas al autor o a bibliotecarios/administradores.
        """
        serializer_class = ReviewSerializer
        permission_classes = [permissions.IsAuthenticated]

        def get_queryset(self):
                queryset = Review.objects.filter(deleted_at__isnull=True)
                user = self.request.user
                is_moderator = user.is_authenticated and (
                        user.rol in [User.Rol.LIBRARIAN, User.Rol.ADMIN]
                        or user.is_staff
                        or user.is_superuser
                )

                # Eliminación permitida a bibliotecarios/admin (moderación) o al propio autor
                if self.action == 'destroy':
                        if is_moderator:
                                return queryset
                        return queryset.filter(user=user)

                # Modificación restringida únicamente al autor
                if self.action in ['update', 'partial_update']:
                        return queryset.filter(user=user)

                # Si se filtra por libro, mostrar todas las reseñas comunitarias de ese libro
                book_id = self.request.query_params.get('book')
                if book_id is not None:
                        if book_id.isdigit():
                                return queryset.filter(book_id=int(book_id))
                        return Review.objects.none()

                # Sin filtro de libro: muestra las reseñas del propio usuario autenticado ("Mis reseñas")
                return queryset.filter(user=user)

        def perform_create(self, serializer):
                # Asigna automáticamente el usuario que hace la solicitud
                serializer.save(user=self.request.user)

        def perform_destroy(self, instance):
                from django.utils import timezone
                # Soft delete para reseñas
                instance.deleted_at = timezone.now()
                instance.save()


# ==========================================
# ENDPOINTS PÚBLICOS DE LIBROS (DISCOVERY / RECOMENDACIÓN)
# ==========================================

class RandomBookView(generics.GenericAPIView):
        """
        Endpoint público que devuelve un libro random (id, titulo, año, tapa, autor).
        GET /api/v1/random/ (o /random/)
        Precondición: No requiere inicio de sesión.
        """
        permission_classes = [permissions.AllowAny]
        serializer_class = BookRecommendationSerializer

        def get(self, request, *args, **kwargs):
                book_ids = list(
                        Book.objects.filter(deleted_at__isnull=True).values_list("id", flat=True)
                )
                if not book_ids:
                        return Response(
                                {"detail": "No se encontraron libros disponibles en el catálogo."},
                                status=status.HTTP_404_NOT_FOUND,
                        )

                random_id = random.choice(book_ids)
                book = (
                        Book.objects.filter(id=random_id, deleted_at__isnull=True)
                        .annotate(
                                avg_rating=Avg(
                                        "reviews__rating",
                                        filter=Q(reviews__deleted_at__isnull=True),
                                )
                        )
                        .prefetch_related("authors", "genres")
                        .first()
                )

                if not book:
                        return Response(
                                {"detail": "El libro seleccionado no se encuentra disponible."},
                                status=status.HTTP_404_NOT_FOUND,
                        )

                serializer = self.get_serializer(book)
                return Response(serializer.data, status=status.HTTP_200_OK)


class BookRecommendationView(generics.GenericAPIView):
        """
        Endpoint público que devuelve los 10 libros con mejor rating (id, titulo, año, tapa, autor).
        GET /api/v1/recommendation/ (o /recommendation/)
        Precondición: No requiere inicio de sesión.
        """
        permission_classes = [permissions.AllowAny]
        serializer_class = BookRecommendationSerializer

        def get(self, request, *args, **kwargs):
                books = (
                        Book.objects.filter(deleted_at__isnull=True)
                        .annotate(
                                avg_rating=Avg(
                                        "reviews__rating",
                                        filter=Q(reviews__deleted_at__isnull=True),
                                ),
                                review_count=Count(
                                        "reviews",
                                        filter=Q(reviews__deleted_at__isnull=True),
                                ),
                        )
                        .order_by(
                                F("avg_rating").desc(nulls_last=True),
                                F("review_count").desc(),
                                "-id",
                        )
                        .prefetch_related("authors", "genres")[:10]
                )

                serializer = self.get_serializer(books, many=True)
                return Response(serializer.data, status=status.HTTP_200_OK)

