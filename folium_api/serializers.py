from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import * # Importamos todos los modelos del archivo `models.py` (que está en este mismo directorio)

# Crear serializadores acá
# Para más info copada referirse a: https://www.django-rest-framework.org/tutorial/1-serialization/

# Un serializador convierte la información de la base de datos a formato JSON (y viceversa),
# para que la aplicación frontend o móvil pueda leerla y enviarla fácilmente.
#
# Ejemplo de uso:
# class ProductoSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Producto
#         fields = '__all__'  # Incluye todos los campos del modelo



User = get_user_model()


# ==========================================
# SERIALIZERS BÁSICOS
# ==========================================


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = [
            "id",
            "name",
            "last_name",
            "biography",
        ]


class AuthorSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = [
            "id",
            "name",
            "last_name",
        ]


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = [
            "id",
            "name",
            "description",
        ]


class GenreSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = [
            "id",
            "name",
        ]


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "rol",
            "password",
            "is_active",
            "date_joined",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "date_joined",
            "updated_at",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attribute, value in validated_data.items():
            setattr(instance, attribute, value)

        if password:
            instance.set_password(password)

        instance.save()
        return instance


class UserSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "rol",
        ]

    def get_full_name(self, obj):
        return obj.get_full_name()


# ==========================================
# ITEMS
# ==========================================


class ItemSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Item
        fields = [
            "id",
            "book",
            "inventory_code",
            "status",
            "status_display",
            "location",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class ItemSummarySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Item
        fields = [
            "id",
            "inventory_code",
            "status",
            "status_display",
            "location",
        ]


# ==========================================
# LIBROS
# ==========================================


class BookSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "cover_image",
        ]


class BookWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "isbn",
            "description",
            "publication_year",
            "cover_image",
            "authors",
            "genres",
        ]
        read_only_fields = [
            "id",
        ]


class BookListSerializer(serializers.ModelSerializer):
    authors = AuthorSummarySerializer(
        many=True,
        read_only=True,
    )
    genres = GenreSummarySerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "isbn",
            "publication_year",
            "cover_image",
            "authors",
            "genres",
        ]


class BookDetailSerializer(serializers.ModelSerializer):
    authors = AuthorSerializer(
        many=True,
        read_only=True,
    )
    genres = GenreSerializer(
        many=True,
        read_only=True,
    )
    items = ItemSummarySerializer(
        many=True,
        read_only=True,
    )
    total_items = serializers.SerializerMethodField()
    available_items = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "isbn",
            "description",
            "publication_year",
            "cover_image",
            "authors",
            "genres",
            "items",
            "total_items",
            "available_items",
            "created_at",
            "updated_at",
        ]

    def get_total_items(self, obj):
        return obj.items.count()

    def get_available_items(self, obj):
        return obj.items.filter(
            status=Item.Status.AVAILABLE
        ).count()


# ==========================================
# PRÉSTAMOS
# ==========================================


class LoanWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = [
            "id",
            "item",
            "user",
            "loaned_at",
            "due_at",
            "returned_at",
        ]
        read_only_fields = [
            "id",
        ]


class LoanReadSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(
        source="item.inventory_code",
        read_only=True,
    )
    book = BookSimpleSerializer(
        source="item.book",
        read_only=True,
    )
    user = UserSummarySerializer(
        read_only=True,
    )

    class Meta:
        model = Loan
        fields = [
            "id",
            "item",
            "item_code",
            "book",
            "user",
            "loaned_at",
            "due_at",
            "returned_at",
        ]


# ==========================================
# RESERVAS
# ==========================================


class ReservationSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    book_detail = BookSimpleSerializer(
        source="book",
        read_only=True,
    )
    user_detail = UserSummarySerializer(
        source="user",
        read_only=True,
    )

    class Meta:
        model = Reservation
        fields = [
            "id",
            "book",
            "book_detail",
            "user",
            "user_detail",
            "status",
            "status_display",
            "expires_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


# ==========================================
# RESEÑAS
# ==========================================


class ReviewSerializer(serializers.ModelSerializer):
    user_detail = UserSummarySerializer(
        source="user",
        read_only=True,
    )
    book_detail = BookSimpleSerializer(
        source="book",
        read_only=True,
    )

    class Meta:
        model = Review
        fields = [
            "id",
            "book",
            "book_detail",
            "user",
            "user_detail",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]