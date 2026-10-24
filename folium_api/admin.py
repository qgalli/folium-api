from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from .models import *

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'dni', 'email', 'first_name', 'last_name', 'rol', 'is_staff')

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('name', 'last_name')
    search_fields = ('name', 'last_name')

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

class ItemInline(admin.TabularInline):
    model = Item
    extra = 1

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'isbn', 'publication_year')
    search_fields = ('title', 'isbn')
    list_filter = ('genres', 'publication_year')
    filter_horizontal = ('authors', 'genres')
    inlines = [ItemInline]

@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'inventory_code', 'book', 'status', 'location')
    list_filter = ('status', 'location')
    search_fields = ('inventory_code', 'book__title')
    autocomplete_fields = ('book',) 

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = CustomUserCreationForm
    list_display = ('first_name', 'last_name', 'dni', 'email', 'rol')
    list_filter = ('rol',)
    search_fields = ('first_name', 'last_name', 'email', 'dni')
    ordering = ('username',)
    # Pantalla de edición de un usuario existente
    fieldsets = (
        ('Credentials', {'fields': ('username', 'password')}),
        ('Personal Information', {'fields': ('first_name', 'last_name', 'dni', 'email', 'rol')}),
        ('Access Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser'),
            'description': 'Nota: Un LIBRARIAN requiere tener "is_staff" tildado para poder ingresar a este panel.'
        }),
        ('Audit', {'fields': ('date_joined', 'deleted_at')}),
    )
    # Pantalla de creación de nuevo usuario (con password1 y password2 con hashing)
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'dni', 'email', 'first_name', 'last_name', 'rol', 'is_staff', 'password1', 'password2'),
        }),
    )

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'item', 'loaned_at', 'due_at', 'returned_at')
    list_filter = ('loaned_at', 'returned_at')
    search_fields = ('user__email', 'item__inventory_code')
    autocomplete_fields = ('user', 'item')

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'book', 'user', 'status', 'expires_at')
    list_filter = ('status', 'expires_at')
    search_fields = ('book__title', 'user__email')

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('book', 'user', 'rating', 'created_at')
    list_filter = ('rating',)
    search_fields = ('book__title', 'user__email')