from django.contrib.auth.models import AbstractUser
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
import re

# Create your models here.

class Author(models.Model):
    name = models.CharField(max_length=45)
    last_name = models.CharField(max_length=45)
    biography = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        errors = {}

        # Regla 1: El nombre solo debe contener letras, espacios, apóstrofes y guiones
        if self.name and not re.match(r"^[a-zA-ZÀ-ÿ\s'-]+$", self.name):
            errors['name'] = 'El nombre solo puede contener letras, espacios, apóstrofes y guiones.'

        # Regla 2: El apellido solo debe contener letras, espacios, apóstrofes y guiones
        if self.last_name and not re.match(r"^[a-zA-ZÀ-ÿ\s'-]+$", self.last_name):
            errors['last_name'] = 'El apellido solo puede contener letras, espacios, apóstrofes y guiones.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} {self.last_name}"
    
class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

class Book(models.Model):
    authors = models.ManyToManyField(
        Author, 
        related_name="books"
    )
    
    genres = models.ManyToManyField(
        Genre, 
        related_name="books"
    )
    
    title = models.CharField(max_length=45)
    isbn = models.CharField(max_length=13, unique=True)
    description = models.TextField(blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    cover_image = models.ImageField(upload_to='books/covers/', blank=True, null=True)

    def clean(self):
        errors = {}

        # Regla 1: El ISBN debe tener exactamente 10 o 13 dígitos numéricos
        if self.isbn:
            isbn_digits = self.isbn.replace('-', '').replace(' ', '')
            if not isbn_digits.isdigit() or len(isbn_digits) not in (10, 13):
                errors['isbn'] = 'El ISBN debe contener exactamente 10 o 13 dígitos numéricos.'

        # Regla 2: El año de publicación debe ser razonable
        if self.publication_year is not None:
            current_year = timezone.now().year
            if self.publication_year < 868:
                # El libro impreso más antiguo data del año 868 d.C.
                errors['publication_year'] = 'El año de publicación no puede ser anterior a 868.'
            elif self.publication_year > current_year:
                errors['publication_year'] = f'El año de publicación no puede ser posterior al año actual ({current_year}).'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title
    
class Item(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponible"
        LOANED = "LOANED", "Prestado"
        RESERVED = "RESERVED", "Reservado"
        DAMAGED = "DAMAGED", "Dañado"
        LOST = "LOST", "Perdido"
    
    book = models.ForeignKey(
        Book, 
        on_delete=models.PROTECT,
        related_name="items"
    )
    
    inventory_code = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    location = models.CharField(max_length=45, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        errors = {}

        # Regla 1: Un ítem LOST o DAMAGED no puede volver a AVAILABLE directamente
        if self.pk:
            try:
                original = Item.objects.get(pk=self.pk)
                estados_bloqueados = {Item.Status.LOST, Item.Status.DAMAGED}
                if original.status in estados_bloqueados and self.status == Item.Status.AVAILABLE:
                    errors['status'] = (
                        f'Un ítem en estado "{original.get_status_display()}" no puede pasar directamente '
                        f'a "Disponible". Debe ser revisado primero.'
                    )
            except Item.DoesNotExist:
                pass

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.inventory_code

class User(AbstractUser):
    class Rol(models.TextChoices):
        LIBRARIAN = "LIBRARIAN", "Bibliotecario"
        USER = "USER", "Usuario"
        ADMIN = "ADMIN", "Administrador"

    # AbstractUser ya provee estos campos de forma automática:
    # - username: nombre de usuario para iniciar sesión
    # - first_name / last_name: nombre y apellido
    # - email: correo electrónico
    # - password: contraseña ya hasheada (nunca se guarda en texto plano)
    # - is_active: si el usuario está activo o no (útil para soft delete)
    # - date_joined: cuándo se registró

    # Sobreescribimos email para que sea único y requerido
    email = models.EmailField(unique=True)

    # Campos propios del proyecto
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.USER)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    favorites = models.ManyToManyField(
        'Book', 
        related_name='favorited_by', 
        blank=True
    )

    def clean(self):
        super().clean()
        errors = {}

        # Regla 1: El nombre solo debe contener letras, espacios, apóstrofes y guiones
        if self.first_name and not re.match(r"^[a-zA-ZÀ-ÿ\s'-]+$", self.first_name):
            errors['first_name'] = 'El nombre solo puede contener letras, espacios, apóstrofes y guiones.'

        # Regla 2: El apellido solo debe contener letras, espacios, apóstrofes y guiones
        if self.last_name and not re.match(r"^[a-zA-ZÀ-ÿ\s'-]+$", self.last_name):
            errors['last_name'] = 'El apellido solo puede contener letras, espacios, apóstrofes y guiones.'

        # Regla 3: La fecha de eliminación (soft-delete) no puede ser en el futuro
        if self.deleted_at and self.deleted_at > timezone.now():
            errors['deleted_at'] = 'La fecha de eliminación no puede ser en el futuro.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"



class Loan(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="loans")
    # Usamos settings.AUTH_USER_MODEL para apuntar siempre al modelo de usuario activo del proyecto
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loans")
    loaned_at = models.DateTimeField()
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        errors = {}

        # Regla 1: La fecha de vencimiento debe ser posterior a la fecha de préstamo
        if self.due_at and self.loaned_at:
            if self.due_at <= self.loaned_at:
                errors['due_at'] = 'La fecha de vencimiento debe ser posterior a la fecha de inicio del préstamo.'

        # Regla 2: La fecha de devolución (si existe) debe ser posterior a la fecha de préstamo
        if self.returned_at and self.loaned_at:
            if self.returned_at < self.loaned_at:
                errors['returned_at'] = 'La fecha de devolución no puede ser anterior a la fecha de inicio del préstamo.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Loan #{self.id} - User: {self.user.get_full_name()} - Item: {self.item.inventory_code}"

class Reservation(models.Model):
    class StatusReservation(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        COMPLETED = 'COMPLETED', 'Completado'
        CANCELED = 'CANCELLED', 'Cancelado'
        EXPIRED = 'EXPIRED', 'Expirado'

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reservations')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reservations')
    status = models.CharField(max_length=20, choices=StatusReservation.choices, default=StatusReservation.PENDING)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        errors = {}

        # Regla 1: La fecha de expiración debe ser en el futuro al crear la reserva
        if not self.pk and self.expires_at:
            if self.expires_at <= timezone.now():
                errors['expires_at'] = 'La fecha de expiración debe ser en el futuro.'

        # Regla 2: Un usuario no puede tener dos reservas PENDING para el mismo libro
        if self.user_id and self.book_id:
            reserva_duplicada = Reservation.objects.filter(
                user_id=self.user_id,
                book_id=self.book_id,
                status=Reservation.StatusReservation.PENDING
            ).exclude(pk=self.pk).exists()
            if reserva_duplicada:
                errors['book'] = 'Ya existe una reserva pendiente para este libro por parte del usuario.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Reservation #{self.id} - Book: {self.book.title}"

class Review(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    def clean(self):
        errors = {}

        # Regla 1: El rating debe estar entre 1 y 5
        if self.rating is not None:
            if not (1 <= self.rating <= 5):
                errors['rating'] = 'La calificación debe ser un valor entre 1 y 5.'

        # Regla 2: Un usuario no puede dejar más de una reseña activa por libro
        if self.user_id and self.book_id:
            resena_duplicada = Review.objects.filter(
                user_id=self.user_id,
                book_id=self.book_id,
                deleted_at__isnull=True
            ).exclude(pk=self.pk).exists()
            if resena_duplicada:
                errors['book'] = 'El usuario ya tiene una reseña activa para este libro.'

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Review by {self.user.get_full_name()} for {self.book.title} ({self.rating}/5)"