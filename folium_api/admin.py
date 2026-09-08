from django.contrib import admin
from .models import *

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
    list_display = ('inventory_code', 'book', 'status', 'location')
    list_filter = ('status', 'location')
    search_fields = ('inventory_code', 'book__title')
    autocomplete_fields = ('book',) 

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('name', 'last_name', 'email', 'rol')
    list_filter = ('rol',)
    search_fields = ('name', 'last_name', 'email')

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