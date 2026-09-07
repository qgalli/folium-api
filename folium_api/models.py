from django.db import models

# Create your models here.

class Author(models.Model):
    name = models.CharField(max_length=45)
    last_name = models.CharField(max_length=45)
    biography = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
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
    decription = models.TextField(blank=True)
    publication_year = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
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
        related_name="copies"
    )
    
    inventory_code = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.inventory_code

class User(models.Model):
    class Rol(models.TextChoices):
        LIBRIAN = "LIBRIAN", "Bibliotecario"
        USER = "USER", "Usuario"
        ADMIN = "ADMIN", "Administrador"

    name = models.CharField(max_length=45)
    last_name = models.CharField(max_length=45)
    email = models.EmailField(unique=True, max_length=45)
    password_hash = models.CharField(max_length=45)
    rol = models.CharField(max_length=20, choices=Rol.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)