from django.views import View
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
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
# ==========================================
# view Librian
# ==========================================

class ItemViewSet(viewsets.ModelViewSet):
    
        """
        Controlador para que el bibliotecario gestione el inventario 
        de ejemplares físicos (copias de los libros).
        """
        queryset= Item.objects.all()  # 1. ¿De dónde saca la información?
        serializer_class = ItemSerializer  # 2. ¿Qué traductor JSON usa?
        permission_classes= [IsLibrarian]     # 3. ¿Quién tiene permisos de acceso?

class LoanViewSet(viewsets.ModelViewSet):
        """
        Controlador para que el bibliotecario gestione el prestamo
        """
        queryset= Loan.objects.all()
        serializer_class = LoanWriteSerializer
        permission_classes = [IsLibrarian]

class BookViewSet(viewsets.ModelViewSet):
        """
        Controlador para que el bibliotecario gestione los libros
        """
        queryset= Book.objects.all()
        serializer_class = BookWriteSerializer
        permission_classes = [IsLibrarian]

class AuthorViewSet(viewsets.ModelViewSet):
        """
        Controlador para que el bibliotecario gestione los autores
        """
        queryset= Author.objects.all()
        serializer_class = AuthorSerializer
        permission_classes = [IsLibrarian]

class GenreViewSet(viewsets.ModelViewSet):
        """
        Controlador para que el bibliotecario gestione Generos
        """
        queryset= Genre.objects.all()
        serializer_class = GenreSerializer
        permission_classes = [IsLibrarian]