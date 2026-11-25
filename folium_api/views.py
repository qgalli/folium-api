from django.views import View
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, permissions, status, pagination, throttling
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView
import random
import re
from django.db import transaction
from django.db.models import (
        Avg,
        Case,
        Count,
        DateTimeField,
        Exists,
        F,
        IntegerField,
        OuterRef,
        Q,
        Value,
        When,
)
from django.db.models.functions import Concat, Lower
from django.utils import timezone
from .models import *
from .passwords import generate_temporary_password
from .serializers import *
from rest_framework.exceptions import ValidationError
from .permissions import (
        is_admin,
        is_librarian_or_admin,
        IsLibrarianOrReadOnly,
        IsLibrarianOrPublicReadOnly,
        IsLibrarianOrAdminUser,
)

# Create your views here.

PG_INT_MIN = 1
PG_INT_MAX = 2_147_483_647


def parse_pg_int(raw_value, field_name, min_value=PG_INT_MIN, max_value=PG_INT_MAX):
        """Parsea un entero dentro del rango int32 de PostgreSQL o lanza 400."""
        value_str = str(raw_value).strip() if raw_value is not None else ''
        if not re.fullmatch(r'[+-]?\d+', value_str):
                raise ValidationError({
                        field_name: f"El parámetro '{field_name}' debe ser un número entero válido."
                })
        parsed = int(value_str)
        if parsed < min_value or parsed > max_value:
                raise ValidationError({
                        field_name: f"El parámetro '{field_name}' debe estar entre {min_value} y {max_value}."
                })
        return parsed


def try_parse_pg_int(raw_value, min_value=PG_INT_MIN, max_value=PG_INT_MAX):
        """Retorna el int32 válido si raw_value representa dígitos en rango; si no, None."""
        if not raw_value:
                return None
        value_str = str(raw_value).strip()
        if not value_str.isdigit() or len(value_str) > 10:
                return None
        parsed = int(value_str)
        if min_value <= parsed <= max_value:
                return parsed
        return None

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
        permission_classes = [IsLibrarianOrAdminUser]
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
                book_param = self.request.query_params.get('book')

                if book_param:
                        qs = qs.filter(book_id=parse_pg_int(book_param, 'book'))

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

        def perform_destroy(self, instance):
                if (
                        instance.status == Item.Status.LOANED
                        or Loan.objects.filter(item=instance, returned_at__isnull=True).exists()
                ):
                        raise ValidationError(
                                "No se puede eliminar el ejemplar porque tiene un préstamo activo sin devolver."
                        )

                has_active_reservation = (
                        Reservation.objects.filter(
                                item=instance,
                                status=Reservation.StatusReservation.PENDING,
                        )
                        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                        .exists()
                )
                if has_active_reservation:
                        raise ValidationError(
                                "No se puede eliminar el ejemplar porque tiene una reserva pendiente vigente."
                        )

                instance.delete()

        @action(
                detail=True,
                methods=['post'],
                permission_classes=[IsLibrarianOrAdminUser],
                url_path='mark-reviewed',
                url_name='mark-reviewed',
        )
        def mark_reviewed(self, request, pk=None):
                """Rehabilita a AVAILABLE un ejemplar DAMAGED o LOST tras revisión física."""
                target = self.get_object()
                with transaction.atomic():
                        item = Item.objects.select_for_update().select_related('book').get(pk=target.pk)

                        if item.status not in (Item.Status.DAMAGED, Item.Status.LOST):
                                raise ValidationError({
                                        "status": "Solo se pueden rehabilitar ejemplares en estado Dañado o Perdido."
                                })

                        if item.book.deleted_at is not None:
                                raise ValidationError({
                                        "book": "No se puede rehabilitar un ejemplar cuyo libro fue eliminado."
                                })

                        if item.loans.filter(returned_at__isnull=True).exists():
                                raise ValidationError({
                                        "status": "El ejemplar tiene un préstamo activo sin devolver."
                                })

                        has_active_reservation = (
                                item.reservations.filter(status=Reservation.StatusReservation.PENDING)
                                .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
                                .exists()
                        )
                        if has_active_reservation:
                                raise ValidationError({
                                        "status": "El ejemplar tiene una reserva pendiente vigente."
                                })

                        item.status = Item.Status.AVAILABLE
                        item.save(update_fields=['status', 'updated_at'])

                refreshed = self.get_queryset().get(pk=item.pk)
                serializer = ItemReadSerializer(refreshed, context=self.get_serializer_context())
                return Response(serializer.data, status=status.HTTP_200_OK)

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
                        user_id = try_parse_pg_int(user_search)
                        if user_id is not None:
                                user_query |= Q(user_id=user_id)
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
                        item_id = try_parse_pg_int(item_search)
                        if item_id is not None:
                                item_query |= Q(item_id=item_id)
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


class AvailableBooksPagination(pagination.PageNumberPagination):
        page_size = 50
        page_size_query_param = 'page_size'
        max_page_size = 100


class BookViewSet(viewsets.ModelViewSet):
        """
        Controlador para gestionar los libros (catálogo).
        Permite lectura a lectores y gestión completa al bibliotecario.
        """
        queryset = Book.objects.filter(deleted_at__isnull=True).select_related('editorial').prefetch_related('authors', 'genres')
        serializer_class = BookWriteSerializer
        permission_classes = [IsLibrarianOrPublicReadOnly]
        pagination_class = BookPagination

        def get_queryset(self):
                user = self.request.user
                is_staff_or_lib = is_librarian_or_admin(user)
                deleted_only = self.request.query_params.get('deleted_only') in ['true', '1', 'True']
                include_deleted = self.request.query_params.get('include_deleted') in ['true', '1', 'True']

                if is_staff_or_lib and deleted_only:
                        qs = Book.objects.filter(deleted_at__isnull=False)
                elif is_staff_or_lib and include_deleted:
                        qs = Book.objects.all()
                else:
                        qs = Book.objects.filter(deleted_at__isnull=True)

                qs = qs.select_related('editorial').prefetch_related('authors', 'genres')
                if self.action in ['list', 'retrieve']:
                        qs = qs.prefetch_related('items', 'reservations')

                genre = self.request.query_params.get('genre')
                year = self.request.query_params.get('year')
                search = self.request.query_params.get('search') or self.request.query_params.get('q')

                if genre:
                        qs = qs.filter(genres__name__icontains=genre)
                if year:
                        qs = qs.filter(publication_year=parse_pg_int(year, 'year'))
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

                available_only = self.request.query_params.get('available_only')
                if available_only in ['true', '1', 'True']:
                        qs = qs.filter(items__status=Item.Status.AVAILABLE)

                # distinct() evita libros duplicados cuando hay múltiples autores/géneros
                return qs.distinct()

        def get_serializer_class(self):
                if self.action == 'list':
                        return BookListSerializer
                elif self.action == 'retrieve':
                        return BookDetailSerializer
                return BookWriteSerializer

        def perform_destroy(self, instance):
                from django.db.models import ProtectedError

                # Regla 1: No se puede eliminar si hay préstamos activos (ítem no devuelto)
                has_active_loans = Loan.objects.filter(
                        item__book=instance,
                        returned_at__isnull=True,
                ).exists()
                if has_active_loans:
                        raise ValidationError(
                                "No se puede eliminar el libro porque tiene préstamos activos sin devolver."
                        )

                # Regla 2: No se puede eliminar si hay reservas pendientes vigentes
                has_pending_reservations = instance.reservations.filter(
                        status=Reservation.StatusReservation.PENDING,
                ).exists()
                if has_pending_reservations:
                        raise ValidationError(
                                "No se puede eliminar el libro porque tiene reservas pendientes."
                        )

                # Regla 3: Si tiene ítems (sin préstamos activos ni reservas), el PROTECT
                # de la BD lo bloquearía igualmente → se captura y se informa con claridad.
                try:
                        # Soft delete: marca como eliminado sin borrar el registro físicamente
                        instance.deleted_at = timezone.now()
                        instance.save(update_fields=["deleted_at"])
                except ProtectedError:
                        raise ValidationError(
                                "No se puede eliminar el libro porque tiene ejemplares registrados en el inventario. "
                                "Eliminá primero todos los ejemplares asociados."
                        )

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

        @action(detail=False, methods=['get'], permission_classes=[IsLibrarianOrPublicReadOnly], url_path='options', url_name='options')
        def book_options(self, request, *args, **kwargs):
                """
                Endpoint liviano sin paginación (máximo 50 resultados) para alimentar
                selectores y buscadores en formularios (ItemForm, ItemEditModal).
                Soporta búsqueda por texto con ?search= o ?q=.
                """
                qs = Book.objects.filter(deleted_at__isnull=True)
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

        @action(
                detail=False,
                methods=['get'],
                permission_classes=[IsLibrarianOrReadOnly],
                pagination_class=AvailableBooksPagination,
                url_path='available',
        )
        def available_books(self, request, *args, **kwargs):
                """
                Devuelve la lista de libros que tienen al menos un ejemplar disponible (Item AVAILABLE),
                incluyendo los ítems disponibles para selección directa en mostrador.
                Soporta búsqueda por texto con ?search= o ?q= (título, isbn, autor o código de ejemplar).
                """
                qs = Book.objects.filter(
                        deleted_at__isnull=True,
                        items__status=Item.Status.AVAILABLE
                ).select_related('editorial').prefetch_related('authors', 'genres', 'items').distinct()

                search = request.query_params.get('search') or request.query_params.get('q')
                if search:
                        search = search.strip()
                        matching_authors = Author.objects.filter(
                                books=OuterRef('pk')
                        ).annotate(
                                author_full_name=Concat(
                                        F('name'),
                                        Value(' '),
                                        F('last_name'),
                                )
                        ).filter(
                                Q(name__icontains=search) |
                                Q(last_name__icontains=search) |
                                Q(author_full_name__icontains=search)
                        )
                        matching_items = Item.objects.filter(
                                book_id=OuterRef('pk'),
                                inventory_code__icontains=search,
                        )
                        qs = qs.annotate(
                                matches_author=Exists(matching_authors),
                                matches_item=Exists(matching_items),
                        ).filter(
                                Q(title__icontains=search) |
                                Q(isbn__icontains=search) |
                                Q(matches_author=True) |
                                Q(matches_item=True)
                        )

                qs = qs.order_by('title', 'id')
                page = self.paginate_queryset(qs)
                serializer = BookAvailableOptionSerializer(
                                page,
                                many=True,
                                context={'request': request},
                )
                return self.get_paginated_response(serializer.data)

        @action(detail=True, methods=['post'], permission_classes=[IsLibrarianOrAdminUser], url_path='restore')
        def restore(self, request, pk=None):
                """
                Restaura un libro que fue dado de baja (soft deleted).
                Permite al bibliotecario o administrador recuperarlo en el catálogo.
                """
                try:
                        book = Book.objects.get(pk=pk, deleted_at__isnull=False)
                except Book.DoesNotExist:
                        return Response(
                                {"detail": "No se encontró un libro eliminado con este ID."},
                                status=status.HTTP_404_NOT_FOUND
                        )

                book.deleted_at = None
                book.save(update_fields=["deleted_at"])
                serializer = BookDetailSerializer(book, context={'request': request})
                return Response(serializer.data, status=status.HTTP_200_OK)


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

        def create(self, request, *args, **kwargs):
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                favorite, created = User.favorites.through.objects.get_or_create(
                        user=request.user,
                        book=serializer.validated_data['book'],
                )
                output_serializer = self.get_serializer(favorite)
                headers = self.get_success_headers(output_serializer.data) if created else {}
                return Response(
                        output_serializer.data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
                        headers=headers,
                )

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


class ChangePasswordView(generics.GenericAPIView):
        serializer_class = ChangePasswordSerializer
        permission_classes = [permissions.IsAuthenticated]

        def post(self, request, *args, **kwargs):
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)

                request.user.set_password(serializer.validated_data['new_password'])
                request.user.save(update_fields=['password'])

                return Response(
                        {"detail": "La contraseña se actualizó correctamente."},
                        status=status.HTTP_200_OK,
                )


class UserViewSet(viewsets.ModelViewSet):
        """
        Controlador para que los bibliotecarios y administradores gestionen
        los usuarios del sistema (búsqueda por DNI para préstamos en mostrador y alta de lectores).
        """
        queryset = User.objects.filter(deleted_at__isnull=True).order_by('-date_joined')
        serializer_class = UserSerializer
        permission_classes = [IsLibrarianOrAdminUser]

        def get_queryset(self):
                qs = User.objects.filter(deleted_at__isnull=True)
                if not is_admin(self.request.user):
                        qs = qs.exclude(Q(rol=User.Rol.ADMIN) | Q(is_superuser=True))
                dni = self.request.query_params.get('dni')
                search = self.request.query_params.get('search') or self.request.query_params.get('q')
                rol = self.request.query_params.get('rol')

                if dni:
                        qs = qs.filter(dni=parse_pg_int(dni, 'dni'))

                if rol:
                        qs = qs.filter(rol=rol)

                if search:
                        search = search.strip()
                        qs = qs.filter(
                                Q(dni__icontains=search) |
                                Q(username__icontains=search) |
                                Q(first_name__icontains=search) |
                                Q(last_name__icontains=search) |
                                Q(email__icontains=search)
                        )

                return qs.order_by('-date_joined')

        @action(detail=False, methods=['get'], url_path=r'by-dni/(?P<dni>\d+)')
        def by_dni(self, request, dni=None):
                dni_int = parse_pg_int(dni, 'dni')
                try:
                        qs = User.objects.filter(deleted_at__isnull=True)
                        if not is_admin(request.user):
                                qs = qs.exclude(Q(rol=User.Rol.ADMIN) | Q(is_superuser=True))
                        user = qs.get(dni=dni_int)
                        serializer = UserSerializer(user, context={'request': request})
                        active_loans_count = Loan.objects.filter(user=user, returned_at__isnull=True).count()
                        data = serializer.data
                        data['active_loans_count'] = active_loans_count
                        data['full_name'] = user.get_full_name() or user.username
                        return Response(data, status=status.HTTP_200_OK)
                except User.DoesNotExist:
                        return Response(
                                {"detail": f"No se encontró ningún lector con el DNI {dni}."},
                                status=status.HTTP_404_NOT_FOUND
                        )

        def create(self, request, *args, **kwargs):
                data = request.data.copy()
                temporary_password = None
                if 'rol' not in data or not data['rol']:
                        data['rol'] = User.Rol.USER

                if not data.get('password'):
                        temporary_password = generate_temporary_password()
                        data['password'] = temporary_password

                # Si no se provee username, generarlo automáticamente a partir del DNI o nombre
                if not data.get('username') or not str(data.get('username')).strip():
                        dni_val = data.get('dni', '')
                        first_name = (data.get('first_name') or '').strip().lower()
                        base_username = f"{first_name}_{dni_val}" if first_name and dni_val else f"lector_{dni_val}" if dni_val else "lector"
                        candidate = re.sub(r'[^a-zA-Z0-9_]', '', base_username)
                        counter = 1
                        while User.objects.filter(username__iexact=candidate).exists():
                                candidate = f"{base_username}_{counter}"
                                counter += 1
                        data['username'] = candidate

                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                headers = self.get_success_headers(serializer.data)

                resp_data = serializer.data
                resp_data['active_loans_count'] = 0
                user_obj = serializer.instance
                resp_data['full_name'] = user_obj.get_full_name() or user_obj.username
                if temporary_password:
                        resp_data['temporary_password'] = temporary_password

                return Response(resp_data, status=status.HTTP_201_CREATED, headers=headers)


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

        def filter_queryset_for_list(self, queryset):
                params = self.request.query_params
                user_search = params.get('user', '').strip()
                book_search = params.get('book', '').strip()
                status_filter = params.get('status', '').strip().lower()
                ordering = params.get('ordering', '-created_at')

                if user_search:
                        user_query = (
                                Q(user__first_name__icontains=user_search)
                                | Q(user__last_name__icontains=user_search)
                                | Q(user__username__icontains=user_search)
                                | Q(user__email__icontains=user_search)
                                | Q(user_full_name__icontains=user_search)
                        )
                        user_id = try_parse_pg_int(user_search)
                        if user_id is not None:
                                user_query |= Q(user_id=user_id)
                        queryset = queryset.annotate(
                                user_full_name=Concat(
                                        F('user__first_name'),
                                        Value(' '),
                                        F('user__last_name'),
                                )
                        ).filter(user_query)

                if book_search:
                        book_query = (
                                Q(book__title__icontains=book_search)
                                | Q(book__isbn__icontains=book_search)
                        )
                        book_id = try_parse_pg_int(book_search)
                        if book_id is not None:
                                book_query |= Q(book_id=book_id)
                        queryset = queryset.filter(book_query)

                valid_statuses = {'pending', 'expired', 'completed', 'cancelled'}
                if status_filter and status_filter not in valid_statuses:
                        raise ValidationError({
                                'status': 'Use uno de estos estados: pending, expired, completed, cancelled.'
                        })

                now = timezone.now()
                if status_filter == 'pending':
                        queryset = queryset.filter(
                                status=Reservation.StatusReservation.PENDING,
                                expires_at__gt=now,
                        )
                elif status_filter == 'expired':
                        queryset = queryset.filter(
                                Q(status=Reservation.StatusReservation.EXPIRED)
                                | Q(
                                        status=Reservation.StatusReservation.PENDING,
                                        expires_at__lte=now,
                                )
                        )
                elif status_filter == 'completed':
                        queryset = queryset.filter(
                                status=Reservation.StatusReservation.COMPLETED
                        )
                elif status_filter == 'cancelled':
                        queryset = queryset.filter(
                                status=Reservation.StatusReservation.CANCELED
                        )

                valid_orderings = {'created_at', '-created_at', 'title'}
                if ordering not in valid_orderings:
                        raise ValidationError({
                                'ordering': 'Use created_at, -created_at o title.'
                        })

                if ordering == 'title':
                        return queryset.order_by(Lower('book__title'), 'pk').distinct()

                direction = '-' if ordering == '-created_at' else ''
                queryset = queryset.annotate(
                        reservation_status_order=Case(
                                When(
                                        status=Reservation.StatusReservation.PENDING,
                                        expires_at__gt=now,
                                        then=Value(0),
                                ),
                                When(
                                        status=Reservation.StatusReservation.PENDING,
                                        expires_at__lte=now,
                                        then=Value(1),
                                ),
                                When(
                                        status=Reservation.StatusReservation.EXPIRED,
                                        then=Value(1),
                                ),
                                When(
                                        status=Reservation.StatusReservation.COMPLETED,
                                        then=Value(2),
                                ),
                                default=Value(3),
                                output_field=IntegerField(),
                        )
                )
                return queryset.order_by(
                        'reservation_status_order',
                        f'{direction}created_at',
                        'pk',
                ).distinct()

        def filter_queryset(self, queryset):
                queryset = super().filter_queryset(queryset)
                if self.action == 'list':
                        return self.filter_queryset_for_list(queryset)
                return queryset

        @action(detail=False, methods=['get'])
        def summary(self, request):
                now = timezone.now()
                return Response(
                        self.get_queryset().aggregate(
                                pending=Count(
                                        'pk',
                                        filter=Q(
                                                status=Reservation.StatusReservation.PENDING,
                                                expires_at__gt=now,
                                        ),
                                ),
                                completed=Count(
                                        'pk',
                                        filter=Q(
                                                status=Reservation.StatusReservation.COMPLETED
                                        ),
                                ),
                                cancelled=Count(
                                        'pk',
                                        filter=Q(
                                                status=Reservation.StatusReservation.CANCELED
                                        ),
                                ),
                        )
                )

        def perform_create(self, serializer):
                with transaction.atomic():
                        book = serializer.validated_data.get('book')
                        item = (
                                Item.objects.select_for_update()
                                .filter(
                                        book=book,
                                        status=Item.Status.AVAILABLE,
                                )
                                .order_by('pk')
                                .first()
                        )
                        if not item:
                                raise ValidationError({
                                        'detail': 'No hay ejemplares disponibles para este libro en este momento.'
                                })

                        item.status = Item.Status.RESERVED
                        item.save(update_fields=['status', 'updated_at'])
                        serializer.save(user=self.request.user, item=item)

        @staticmethod
        def _assign_available_item(reservation):
                item = (
                        Item.objects.select_for_update()
                        .filter(
                                book_id=reservation.book_id,
                                status=Item.Status.AVAILABLE,
                        )
                        .order_by('pk')
                        .first()
                )
                if item:
                        item.status = Item.Status.RESERVED
                        item.save(update_fields=['status', 'updated_at'])
                        reservation.item = item
                        reservation.save(update_fields=['item', 'updated_at'])

        @staticmethod
        def _release_reserved_item(reservation):
                item = reservation.item
                if item:
                        if item.status == Item.Status.RESERVED:
                                item.status = Item.Status.AVAILABLE
                                item.save(update_fields=['status', 'updated_at'])
                        reservation.item = None

        def perform_update(self, serializer):
                with transaction.atomic():
                        previous_book_id = serializer.instance.book_id
                        reservation = serializer.save()
                        if (
                                reservation.item_id
                                and (
                                        reservation.status != Reservation.StatusReservation.PENDING
                                        or reservation.book_id != previous_book_id
                                )
                        ):
                                self._release_reserved_item(reservation)
                                reservation.save(update_fields=['item', 'updated_at'])

                        if (
                                reservation.status == Reservation.StatusReservation.PENDING
                                and not reservation.item_id
                        ):
                                self._assign_available_item(reservation)

        def perform_destroy(self, instance):
                # Permite eliminar la reserva si es suya o si es bibliotecario/admin
                user = self.request.user
                if not (is_librarian_or_admin(user) or instance.user_id == user.id):
                        raise permissions.exceptions.PermissionDenied("No tienes permiso para eliminar esta reserva.")
                with transaction.atomic():
                        self._release_reserved_item(instance)
                        instance.delete()

        @action(detail=True, methods=['post', 'patch'], url_path='cancel')
        def cancel(self, request, pk=None):
                """
                Cancela o rechaza una reserva:
                - Lectores: pueden cancelar sus propias reservas pendientes.
                - Bibliotecarios/Admin: pueden cancelar o rechazar cualquier reserva.
                Al cancelarse, el cupo del libro se libera de inmediato (status pasa a CANCELLED).
                """
                reservation = self.get_object()
                user = request.user

                # Verificación de permisos de autoría o rol
                if not (is_librarian_or_admin(user) or reservation.user_id == user.id):
                        return Response(
                                {"detail": "No tienes permiso para cancelar esta reserva."},
                                status=status.HTTP_403_FORBIDDEN
                        )

                # Si ya estaba cancelada o completada
                if reservation.status == Reservation.StatusReservation.CANCELED:
                        return Response(
                                {"detail": "La reserva ya se encuentra cancelada."},
                                status=status.HTTP_400_BAD_REQUEST
                        )
                if reservation.status == Reservation.StatusReservation.COMPLETED:
                        return Response(
                                {"detail": "No se puede cancelar una reserva que ya fue completada (convertida en préstamo)."},
                                status=status.HTTP_400_BAD_REQUEST
                        )

                with transaction.atomic():
                        reservation.status = Reservation.StatusReservation.CANCELED
                        self._release_reserved_item(reservation)
                        reservation.save(update_fields=['status', 'item', 'updated_at'])

                serializer = self.get_serializer(reservation)
                return Response(
                        {
                                "detail": "Reserva cancelada correctamente. El ejemplar queda disponible.",
                                "reservation": serializer.data
                        },
                        status=status.HTTP_200_OK
                )


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
                if book_id is not None and book_id != '':
                        return queryset.filter(book_id=parse_pg_int(book_id, 'book'))

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

                # Optimización de muestreo aleatorio en BD sin cargar listas de IDs a RAM
                qs = qs.distinct()
                total_count = qs.count()
                if total_count == 0:
                        return Response(
                                {"detail": "No se encontraron libros disponibles en el catálogo."},
                                status=status.HTTP_404_NOT_FOUND,
                        )

                random_index = random.randint(0, total_count - 1)
                random_book_id = qs.values_list("id", flat=True)[random_index]

                book = (
                        Book.objects.filter(id=random_book_id, deleted_at__isnull=True)
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
