import re
from datetime import datetime
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
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


class FoliumTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["rol"] = User.Rol.ADMIN if user.is_superuser else user.rol
        return token


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
    def _validate_name_field(self, value, field_label):
        if not isinstance(value, str) or str(value).isdigit():
            raise serializers.ValidationError(f"{field_label} debe ser una cadena de texto válida.")
        
        pattern = r"^[a-zA-ZÀ-ÿ\s'-]+$"
        if not re.match(pattern, str(value)):
            raise serializers.ValidationError(f"{field_label} solo puede contener letras, espacios, apóstrofes y guiones.")
        return value

    def validate_name(self, value):
        return self._validate_name_field(value, "El nombre")

    def validate_last_name(self, value):
        return self._validate_name_field(value, "El apellido")


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
    def validate_name(self, value):
        str_val = str(value).strip()
        
        if str_val.isdigit():
            raise serializers.ValidationError("El nombre del género no puede consistir únicamente de números.")

        # Validación case-insensitive de unicidad
        queryset = Genre.objects.filter(name__iexact=str_val)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
            
        if queryset.exists():
            raise serializers.ValidationError("Ya existe un género registrado con este nombre.")

        return str_val
    

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
    def validate_isbn(self, value):
        clean_isbn = re.sub(r'[\s-]', '', str(value))
        if not clean_isbn.isdigit():
            raise serializers.ValidationError("El ISBN solo puede contener números (y guiones).")
        if len(clean_isbn) not in (10, 13):
            raise serializers.ValidationError("El ISBN debe tener exactamente 10 o 13 dígitos.")
        return value

    def validate_publication_year(self, value):
        current_year = datetime.now().year
        if value > current_year:
            raise serializers.ValidationError(f"El año de publicación no puede ser posterior al año actual ({current_year}).")
        if value < 868:
            raise serializers.ValidationError("El año de publicación no puede ser anterior al año 868 d.C.")
        return value
    

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
    def validate(self, attrs):
        loaned_at = attrs.get("loaned_at")
        due_at = attrs.get("due_at")
        returned_at = attrs.get("returned_at")
        item = attrs.get("item")

        # 1. Validaciones de fechas
        if due_at and loaned_at and due_at <= loaned_at:
            raise serializers.ValidationError({"due_at": "La fecha de vencimiento debe ser posterior a la fecha de inicio del préstamo."})

        if returned_at and loaned_at and returned_at < loaned_at:
            raise serializers.ValidationError({"returned_at": "La fecha de devolución no puede ser anterior a la fecha de inicio del préstamo."})

        # 2. Validación de disponibilidad del ejemplar
        if item:
            # Comprobar si el item ya está en uso o tiene un préstamo activo
            active_loan = Loan.objects.filter(item=item, returned_at__isnull=True)
            if self.instance:
                active_loan = active_loan.exclude(pk=self.instance.pk)

            if active_loan.exists() or item.status != Item.Status.AVAILABLE:
                raise serializers.ValidationError({"item": "El ejemplar seleccionado ya se encuentra prestado o no está disponible."})

        return attrs

    def create(self, validated_data):
        loan = super().create(validated_data)
        # Marcar el ejemplar como PRESTADO al momento del alta
        item = loan.item
        item.status = Item.Status.LOANED
        item.save()
        return loan
    

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