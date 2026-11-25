"""
Permisos de la API de Folium.

Este módulo es la única fuente de verdad de la regla "quién puede gestionar la
biblioteca". Cualquier vista, queryset o permiso que necesite saber si un usuario
es bibliotecario/administrador debe usar `is_librarian_or_admin` en lugar de
repetir la condición.
"""

from rest_framework import permissions

from .models import User


def is_librarian_or_admin(user):
    """
    Devuelve True si el usuario está autenticado y es Bibliotecario (LIBRARIAN),
    Administrador (ADMIN), staff o superusuario.
    """
    if not (user and user.is_authenticated):
        return False

    return bool(
        getattr(user, "rol", None) in [User.Rol.LIBRARIAN, User.Rol.ADMIN]
        or user.is_staff
        or user.is_superuser
    )


def is_admin(user):
    """
    Devuelve True si el usuario está autenticado y es Administrador (ADMIN)
    o superusuario.
    """
    if not (user and user.is_authenticated):
        return False

    return bool(
        getattr(user, "rol", None) == User.Rol.ADMIN
        or user.is_superuser
    )


class IsLibrarianOrAdminUser(permissions.BasePermission):
    """
    Autoriza únicamente a usuarios con rol LIBRARIAN o ADMIN (o staff/superusuario).
    Se usa, por ejemplo, en el importador masivo de catálogos.
    """

    def has_permission(self, request, view):
        return is_librarian_or_admin(request.user)


class IsLibrarianOrReadOnly(permissions.BasePermission):
    """
    Lectura (GET, HEAD, OPTIONS): cualquier usuario autenticado, incluidos los lectores.
    Escritura (POST, PUT, PATCH, DELETE): solo Bibliotecarios o Administradores.
    Los usuarios sin sesión no tienen acceso.
    """

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        return is_librarian_or_admin(request.user)


class IsLibrarianOrPublicReadOnly(permissions.BasePermission):
    """
    Lectura (GET, HEAD, OPTIONS): cualquiera, incluso usuarios sin sesión
    (catálogo público).
    Escritura (POST, PUT, PATCH, DELETE): solo Bibliotecarios o Administradores.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return is_librarian_or_admin(request.user)
