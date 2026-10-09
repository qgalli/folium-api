from django.views import View
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
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
        Controlador para que el bibliotecario gestione el préstamo.
        """
        queryset = Loan.objects.all()
        serializer_class = LoanWriteSerializer
        permission_classes = [IsLibrarian]

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