from django.views import View
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, permissions, status, pagination, throttling
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView
import random
from django.db.models import Avg, Case, Count, DateTimeField, F, IntegerField, Q, Value, When
from django.db.models.functions import Concat, Lower
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import *
from .serializers import *
from .permissions import (
        is_librarian_or_admin,
        IsLibrarianOrReadOnly,
        IsLibrarianOrPublicReadOnly,
)

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

class LoginRateThrottle(throttling.AnonRateThrottle):
        scope = 'auth_login'


class FoliumTokenObtainPairView(TokenObtainPairView):
        serializer_class = FoliumTokenObtainPairSerializer
        throttle_classes = [LoginRateThrottle]




# ==========================================
# VIEWSETS
# ==========================================

class ItemPagination(pagination.PageNumberPagination):
        page_size = 50                       # 50 ejemplares por página
        page_size_query_param = 'page_size' 
        max_page_size = 100


class ItemViewSet(viewsets.ModelViewSet):
        """
        Controlador para que el bibliotecario gestione el inventario 
        de ejemplares físicos (copias de los libros).
        """
        queryset = Item.objects.select_related(
                'book',
                'book__editorial'
        ).prefetch_related(
                'book__authors',
                'book__genres',
                'book__items',
                'book__reservations',
        )
        serializer_class = ItemSerializer
        permission_classes = [IsLibrarianOrReadOnly]
        pagination_class = ItemPagination

        def get_queryset(self):
                qs = Item.objects.select_related(
                        'book',
                        'book__editorial'
                ).prefetch_related(
                        'book__authors',
                        'book__genres',
                        'book__items',
                        'book__reservations',
                )

                search = self.request.query_params.get('search') or self.request.query_params.get('q')
                status_param = self.request.query_params.get('status')
                ordering = self.request.query_params.get('ordering')

                if status_param:
                        qs = qs.filter(status=status_param)

                if search:
                        search = search.strip()
                        qs = qs.annotate(
                                author_full_name=Concat(
                                        F('book__authors__name'),
                                        Value(' '),
                                        F('book__authors__last_name')
                                )
                        ).filter(
                                Q(inventory_code__icontains=search) |
                                Q(location__icontains=search) |
                                Q(book__title__icontains=search) |
                                Q(book__isbn__icontains=search) |
                                Q(book__authors__name__icontains=search) |
                                Q(book__authors__last_name__icontains=search) |
                                Q(author_full_name__icontains=search)
                        )

                if ordering:
                        valid_orderings = [
                                'inventory_code', '-inventory_code',
                                'created_at', '-created_at',
                                'status', '-status',
                                'location', '-location'
                        ]
                        if ordering in valid_orderings:
                                qs = qs.order_by(ordering)
                else:
                        qs = qs.order_by('-created_at')

                return qs.distinct()

        def get_serializer_class(self):
                if self.action in ['list', 'retrieve']:
                        return ItemReadSerializer
                return ItemSerializer

class LoanPagination(pagination.PageNumberPagination):
        page_size = 20
        page_size_query_param = 'page_size'
        max_page_size = 50

        def paginate_queryset(self, queryset, request, view=None):
                self.loan_summary = view.get_loan_summary() if view else {}
                return super().paginate_queryset(queryset, request, view)

        def get_paginated_response(self, data):
                return Response({
                        'count': self.page.paginator.count,
                        'next': self.get_next_link(),
                        'previous': self.get_previous_link(),
                        'results': data,
                        'summary': self.loan_summary,
                })


class LoanViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar los préstamos.
        - Bibliotecarios/Admin: gestión completa de todos los préstamos.
        - Lectores: solo lectura de sus propios préstamos.
        """
        serializer_class = LoanWriteSerializer
        permission_classes = [IsLibrarianOrReadOnly]
        pagination_class = LoanPagination

        def get_loan_summary(self):
                user = self.request.user
                qs = Loan.objects.all()
                if not is_librarian_or_admin(user):
                        qs = qs.filter(user=user)

                now = timezone.now()
                return qs.aggregate(
                        due_today=Count(
                                'pk',
                                filter=Q(
                                        returned_at__isnull=True,
                                        due_at__date=timezone.localdate(now),
                                ),
                        ),
                        due_total=Count(
                                'pk',
                                filter=Q(returned_at__isnull=True),
                        ),
                        overdue=Count(
                                'pk',
                                filter=Q(returned_at__isnull=True, due_at__lt=now),
                        ),
                )

        def get_queryset(self):
                user = self.request.user
                base_qs = Loan.objects.select_related('item__book__editorial', 'user')
                # Bibliotecarios y administradores pueden ver todos los préstamos
                if is_librarian_or_admin(user):
                        qs = base_qs.all()
                # Lectores únicamente pueden ver sus propios préstamos
                elif user.is_authenticated:
                        qs = base_qs.filter(user=user)
                else:
                        return Loan.objects.none()

                if self.action != 'list':
                        return qs

                user_search = self.request.query_params.get('user', '').strip()
                item_search = self.request.query_params.get('item', '').strip()
                status_filter = self.request.query_params.get('status', '').strip().lower()
                ordering = self.request.query_params.get('ordering', '-loaned_at')

                if user_search:
                        user_query = (
                                Q(user__first_name__icontains=user_search)
                                | Q(user__last_name__icontains=user_search)
                                | Q(user__username__icontains=user_search)
                                | Q(user__email__icontains=user_search)
                                | Q(user_full_name__icontains=user_search)
                        )
                        if user_search.isdigit():
                                user_query |= Q(user_id=int(user_search))
                        qs = qs.annotate(
                                user_full_name=Concat(
                                        F('user__first_name'),
                                        Value(' '),
                                        F('user__last_name'),
                                )
                        ).filter(user_query)

                if item_search:
                        item_query = (
                                Q(item__inventory_code__icontains=item_search)
                                | Q(item__book__title__icontains=item_search)
                        )
                        if item_search.isdigit():
                                item_query |= Q(item_id=int(item_search))
                        qs = qs.filter(item_query)

                valid_statuses = {'active', 'overdue', 'returned'}
                if status_filter and status_filter not in valid_statuses:
                        raise ValidationError({
                                'status': 'Use uno de estos estados: active, overdue, returned.'
                        })
                now = timezone.now()
                if status_filter == 'returned':
                        qs = qs.filter(returned_at__isnull=False)
                elif status_filter == 'overdue':
                        qs = qs.filter(returned_at__isnull=True, due_at__lt=now)
                elif status_filter == 'active':
                        qs = qs.filter(returned_at__isnull=True, due_at__gte=now)

                valid_orderings = {
                        'item', 'id', '-id', 'loaned_at', '-loaned_at',
                        'remaining', '-remaining',
                }
                if ordering not in valid_orderings:
                        raise ValidationError({
                                'ordering': 'Ordenamiento inválido.'
                        })

                if ordering == 'item':
                        return qs.order_by(
                                Lower('item__book__title'),
                                Lower('item__inventory_code'),
                                'pk',
                        )
                if ordering in {'id', '-id'}:
                        return qs.order_by(ordering)
                if ordering in {'loaned_at', '-loaned_at'}:
                        return qs.order_by(ordering, 'pk')

                direction = '-' if ordering == '-remaining' else ''
                qs = qs.annotate(
                        loan_status_order=Case(
                                When(returned_at__isnull=False, then=Value(2)),
                                When(due_at__lt=now, then=Value(1)),
                                default=Value(0),
                                output_field=IntegerField(),
                        ),
                        active_due_order=Case(
                                When(returned_at__isnull=True, due_at__gte=now, then=F('due_at')),
                                default=Value(None),
                                output_field=DateTimeField(),
                        ),
                        overdue_due_order=Case(
                                When(returned_at__isnull=True, due_at__lt=now, then=F('due_at')),
                                default=Value(None),
                                output_field=DateTimeField(),
                        ),
                        returned_date_order=Case(
                                When(returned_at__isnull=False, then=F('returned_at')),
                                default=Value(None),
                                output_field=DateTimeField(),
                        ),
                )
                return qs.order_by(
                        'loan_status_order',
                        f'{direction}active_due_order',
                        f'{direction}overdue_due_order',
                        f'{direction}returned_date_order',
                        'pk',
                )

        def get_serializer_class(self):
                if self.action in ['list', 'retrieve']:
                        return LoanReadSerializer
                return LoanWriteSerializer


class BookPagination(pagination.PageNumberPagination):
        page_size = 20                       # Libros que devuelve por defecto
        page_size_query_param = 'page_size' 
        max_page_size = 50                  

class BookViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar los libros (catálogo).
        Permite lectura a lectores y gestión completa al bibliotecario.
        """
        queryset = Book.objects.select_related('editorial').prefetch_related('authors', 'genres')
        serializer_class = BookWriteSerializer
        permission_classes = [IsLibrarianOrPublicReadOnly]
        pagination_class = BookPagination

        def get_queryset(self):
                qs = Book.objects.select_related('editorial').prefetch_related('authors', 'genres')
                if self.action in ['list', 'retrieve']:
                        qs = qs.prefetch_related('items', 'reservations')

                genre = self.request.query_params.get('genre')
                year = self.request.query_params.get('year')
                search = self.request.query_params.get('search') or self.request.query_params.get('q')

                if genre:
                        qs = qs.filter(genres__name__icontains=genre)
                if year:
                        qs = qs.filter(publication_year=year)
                if search:
                        search = search.strip()
                        qs = qs.annotate(
                                author_full_name=Concat(
                                        F('authors__name'),
                                        Value(' '),
                                        F('authors__last_name')
                                )
                        ).filter(
                                Q(title__icontains=search) |
                                Q(isbn__icontains=search) |
                                Q(authors__name__icontains=search) |
                                Q(authors__last_name__icontains=search) |
                                Q(author_full_name__icontains=search)
                        )

                # distinct() evita libros duplicados cuando hay múltiples autores/géneros
                return qs.distinct()

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

        @action(detail=False, methods=['get'], permission_classes=[IsLibrarianOrReadOnly], url_path='options')
        def options(self, request, *args, **kwargs):
                """
                Endpoint liviano sin paginación (máximo 50 resultados) para alimentar
                selectores y buscadores en formularios (ItemForm, ItemEditModal).
                Soporta búsqueda por texto con ?search= o ?q=.
                """
                qs = Book.objects.all()
                search = request.query_params.get('search') or request.query_params.get('q')

                if search:
                        search = search.strip()
                        qs = qs.annotate(
                                author_full_name=Concat(
                                        F('authors__name'),
                                        Value(' '),
                                        F('authors__last_name')
                                )
                        ).filter(
                                Q(title__icontains=search) |
                                Q(isbn__icontains=search) |
                                Q(authors__name__icontains=search) |
                                Q(authors__last_name__icontains=search) |
                                Q(author_full_name__icontains=search)
                        ).distinct()

                qs = qs.only('id', 'title', 'isbn').order_by('title')[:50]
                serializer = BookOptionSerializer(qs, many=True)
                return Response(serializer.data)


class AuthorViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar autores.
        Permite lectura a cualquier usuario (lectura pública) y gestión completa al bibliotecario.
        Sin paginación por defecto para nutrir selectores de formularios.
        Soporta búsqueda por texto con ?search= o ?q=.
        """
        queryset = Author.objects.all()
        serializer_class = AuthorSerializer
        permission_classes = [IsLibrarianOrPublicReadOnly]

        def get_queryset(self):
                qs = Author.objects.all()
                search = self.request.query_params.get('search') or self.request.query_params.get('q')
                if search:
                        search = search.strip()
                        qs = qs.annotate(
                                full_name=Concat(
                                        F('name'),
                                        Value(' '),
                                        F('last_name')
                                )
                        ).filter(
                                Q(name__icontains=search) |
                                Q(last_name__icontains=search) |
                                Q(full_name__icontains=search)
                        )
                return qs


class GenreViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar géneros.
        Permite lectura a cualquier usuario (lectura pública) y gestión completa al bibliotecario.
        Sin paginación por defecto para nutrir checkboxes y selectores de formularios.
        Soporta búsqueda por texto con ?search= o ?q=.
        """
        queryset = Genre.objects.all()
        serializer_class = GenreSerializer
        permission_classes = [IsLibrarianOrPublicReadOnly]

        def get_queryset(self):
                qs = Genre.objects.all()
                search = self.request.query_params.get('search') or self.request.query_params.get('q')
                if search:
                        search = search.strip()
                        qs = qs.filter(name__icontains=search)
                return qs


class EditorialViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar editoriales.
        Permite lectura a cualquier usuario (lectura pública) y gestión completa al bibliotecario.
        Sin paginación por defecto para nutrir selectores de formularios sin recorrer libros.
        Soporta búsqueda por texto con ?search= o ?q=.
        """
        queryset = Editorial.objects.all().order_by('name')
        serializer_class = EditorialSerializer
        permission_classes = [IsLibrarianOrPublicReadOnly]

        def get_queryset(self):
                qs = Editorial.objects.all().order_by('name')
                search = self.request.query_params.get('search') or self.request.query_params.get('q')
                if search:
                        search = search.strip()
                        qs = qs.filter(name__icontains=search)
                return qs

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
                ).select_related('user', 'book__editorial')

        def perform_create(self, serializer):
                # Asocia el favorito a la persona que mandó el token
                serializer.save(user=self.request.user)

# ==========================================
# VISTAS DEL LECTOR
# ==========================================

class ReaderRegistrationView(generics.CreateAPIView):
        """
        Controlador público para el autoregistro de lectores.
        Solo permite el registro con rol USER.
        """
        queryset = User.objects.all()
        serializer_class = UserRegisterSerializer
        permission_classes = [permissions.AllowAny]
        throttle_classes = [LoginRateThrottle]


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
                base_qs = Reservation.objects.select_related('book__editorial', 'user')
                # Bibliotecarios y administradores pueden ver y gestionar todas las reservas
                if is_librarian_or_admin(user):
                        return base_qs.all()
                # Un lector solo ve sus propias reservas
                if user.is_authenticated:
                        return base_qs.filter(user=user)
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
                queryset = Review.objects.filter(deleted_at__isnull=True).select_related('book__editorial', 'user')
                user = self.request.user
                is_moderator = is_librarian_or_admin(user)

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
                qs = Book.objects.filter(deleted_at__isnull=True)
                genre = request.query_params.get("genre")
                if genre:
                        genre_qs = qs.filter(genres__name__icontains=genre)
                        if genre_qs.exists():
                                qs = genre_qs

                book_ids = list(qs.values_list("id", flat=True).distinct())
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
                        .prefetch_related("authors", "genres", "items", "reservations")
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
                        .prefetch_related("authors", "genres", "items", "reservations")[:10]
                )

                serializer = self.get_serializer(books, many=True, context={"request": request})
                return Response(serializer.data, status=status.HTTP_200_OK)
