import re
from datetime import datetime
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db.models import Avg
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

    def validate(self, attrs):
        data = super().validate(attrs)
        
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "rol": User.Rol.ADMIN if self.user.is_superuser else self.user.rol
        }
        
        return data


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


class EditorialSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Editorial
        fields = [
            "id",
            "name",
        ]


class EditorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Editorial
        fields = [
            "id",
            "name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
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
            "dni",
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

    def validate_dni(self, value):
        if value is None:
            raise serializers.ValidationError("El DNI es obligatorio.")
        if value <= 0:
            raise serializers.ValidationError("El DNI debe ser un número positivo.")
        qs = User.objects.filter(dni=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este DNI.")
        return value

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


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    Serializador exclusivo para el autoregistro público de usuarios (Lector / Usuario).
    - Fuerza el rol a USER (Usuario) independientemente de lo que envíe el cliente.
    - Exige y encripta la contraseña de forma segura.
    - Evita que campos privilegiados como is_staff o rol puedan ser manipulados.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        error_messages={
            "required": "La contraseña es obligatoria.",
            "min_length": "La contraseña debe tener al menos 8 caracteres.",
        },
    )
    rol = serializers.CharField(read_only=True, default=User.Rol.USER)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "dni",
            "first_name",
            "last_name",
            "email",
            "password",
            "rol",
        ]
        read_only_fields = [
            "id",
            "rol",
        ]

    def validate_username(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("El nombre de usuario no puede estar vacío.")
        cleaned_value = str(value).strip()
        if User.objects.filter(username__iexact=cleaned_value).exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este nombre de usuario.")
        return cleaned_value

    def validate_email(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("El correo electrónico no puede estar vacío.")
        cleaned_value = str(value).strip()
        if User.objects.filter(email__iexact=cleaned_value).exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este correo electrónico.")
        return cleaned_value

    def validate_dni(self, value):
        if value is None:
            raise serializers.ValidationError("El DNI es obligatorio.")
        if value <= 0:
            raise serializers.ValidationError("El DNI debe ser un número positivo.")
        if User.objects.filter(dni=value).exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este DNI.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        # Aseguramos que siempre sea rol USER y sin privilegios de staff
        validated_data["rol"] = User.Rol.USER
        validated_data["is_staff"] = False
        validated_data["is_superuser"] = False
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


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


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "dni",
            "email",
            "first_name",
            "last_name",
            "rol",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "rol",
            "date_joined",
        ]

    def validate_username(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("El nombre de usuario no puede estar vacío.")
        cleaned_value = str(value).strip()
        user = self.instance
        if User.objects.filter(username__iexact=cleaned_value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este nombre de usuario.")
        return cleaned_value

    def validate_dni(self, value):
        if value is None:
            raise serializers.ValidationError("El DNI es obligatorio.")
        if value <= 0:
            raise serializers.ValidationError("El DNI debe ser un número positivo.")
        user = self.instance
        if User.objects.filter(dni=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este DNI.")
        return value

    def validate_email(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("El correo electrónico no puede estar vacío.")
        cleaned_value = str(value).strip()
        user = self.instance
        if User.objects.filter(email__iexact=cleaned_value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Ya existe un usuario registrado con este correo electrónico.")
        return cleaned_value


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
    editorial = EditorialSummarySerializer(read_only=True)

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "editorial",
            "cover_image",
        ]


class BookWriteSerializer(serializers.ModelSerializer):
    editorial = serializers.PrimaryKeyRelatedField(
        queryset=Editorial.objects.all(),
    )

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "editorial",
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
    editorial = EditorialSummarySerializer(read_only=True)
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
            "editorial",
            "publication_year",
            "cover_image",
            "authors",
            "genres",
        ]


class BookDetailSerializer(serializers.ModelSerializer):
    editorial = EditorialSummarySerializer(read_only=True)
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
            "editorial",
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
        available = obj.items.filter(status=Item.Status.AVAILABLE).count()
        pending_reservations = obj.reservations.filter(
            status=Reservation.StatusReservation.PENDING
        ).count()
        return max(0, available - pending_reservations)



class BookRecommendationSerializer(serializers.ModelSerializer):
    """
    Serializador para endpoints de descubrimiento y recomendación (/random y /recommendations).
    Retorna los datos completos para tarjetas de recomendación y coverflow.
    """
    title = serializers.CharField(read_only=True)
    year = serializers.IntegerField(source="publication_year", read_only=True)
    publication_year = serializers.IntegerField(read_only=True)
    cover = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()
    authors = AuthorSummarySerializer(many=True, read_only=True)
    genres = GenreSummarySerializer(many=True, read_only=True)
    category = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    total_items = serializers.SerializerMethodField()
    available_items = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "isbn",
            "description",
            "year",
            "publication_year",
            "cover",
            "cover_image",
            "author",
            "authors",
            "genres",
            "category",
            "rating",
            "total_items",
            "available_items",
        ]

    def get_cover(self, obj):
        if obj.cover_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.cover_image.url)
            return obj.cover_image.url
        return None

    def get_cover_image(self, obj):
        return self.get_cover(obj)

    def get_author(self, obj):
        authors = obj.authors.all()
        return ", ".join(f"{a.name} {a.last_name}".strip() for a in authors) if authors.exists() else None

    def get_category(self, obj):
        first_genre = obj.genres.first()
        return first_genre.name if first_genre else None

    def get_rating(self, obj):
        avg = getattr(obj, "avg_rating", None)
        if avg is not None:
            return round(float(avg), 2)
        active_reviews = obj.reviews.filter(deleted_at__isnull=True)
        avg_aggregate = active_reviews.aggregate(avg=Avg("rating"))["avg"]
        return round(float(avg_aggregate), 2) if avg_aggregate is not None else None

    def get_total_items(self, obj):
        return obj.items.count()

    def get_available_items(self, obj):
        available = obj.items.filter(status=Item.Status.AVAILABLE).count()
        pending_reservations = obj.reservations.filter(
            status=Reservation.StatusReservation.PENDING
        ).count()
        return max(0, available - pending_reservations)


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
        loaned_at = attrs.get("loaned_at", getattr(self.instance, "loaned_at", None))
        due_at = attrs.get("due_at", getattr(self.instance, "due_at", None))
        returned_at = attrs.get("returned_at", getattr(self.instance, "returned_at", None))
        item = attrs.get("item", getattr(self.instance, "item", None))

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
            
            is_new_or_different_item = not self.instance or self.instance.item != item
            if active_loan.exists() or (is_new_or_different_item and item.status != Item.Status.AVAILABLE):
                raise serializers.ValidationError({"item": "El ejemplar seleccionado ya se encuentra prestado o no está disponible."})
        
        return attrs

    def create(self, validated_data):
        loan = super().create(validated_data)
        # Marcar el ejemplar como PRESTADO al momento del alta
        item = loan.item
        item.status = Item.Status.LOANED
        item.save()
        return loan

    def update(self, instance, validated_data):
        previous_item = instance.item
        loan = super().update(instance, validated_data)
        # Si cambiaron el ejemplar físico, liberamos el anterior
        if previous_item != loan.item:
            previous_item.status = Item.Status.AVAILABLE
            previous_item.save()
        # Si ya tiene fecha de devolución, vuelve a estar DISPONIBLE; si no, queda PRESTADO
        if loan.returned_at is not None:
            loan.item.status = Item.Status.AVAILABLE
        else:
            loan.item.status = Item.Status.LOANED
        loan.item.save()
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
            "user",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(self.instance, "user", None) if self.instance else getattr(request, "user", None)
        book = attrs.get("book", getattr(self.instance, "book", None))
        expires_at = attrs.get("expires_at", getattr(self.instance, "expires_at", None))
        status_val = attrs.get("status", getattr(self.instance, "status", Reservation.StatusReservation.PENDING))

        # Regla 1: La fecha de expiración debe ser en el futuro (al crear o modificar expires_at)
        if (not self.instance or "expires_at" in attrs) and expires_at and expires_at <= timezone.now():
            raise serializers.ValidationError({
                "expires_at": "La fecha de expiración debe ser en el futuro."
            })

        # Regla 2: Un usuario no puede tener dos reservas PENDING para el mismo libro
        if user and user.is_authenticated and book and status_val == Reservation.StatusReservation.PENDING:
            duplicate_qs = Reservation.objects.filter(
                user=user,
                book=book,
                status=Reservation.StatusReservation.PENDING
            )
            if self.instance:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)

            if duplicate_qs.exists():
                raise serializers.ValidationError({
                    "book": "Ya existe una reserva pendiente para este libro por parte del usuario."
                })

        return attrs


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
            "user",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else getattr(self.instance, "user", None)
        book = attrs.get("book", getattr(self.instance, "book", None))
        rating = attrs.get("rating", getattr(self.instance, "rating", None))

        # Regla 1: Rating entre 1 y 5
        if rating is not None and not (1 <= rating <= 5):
            raise serializers.ValidationError({
                "rating": "La calificación debe ser un valor entre 1 y 5."
            })

        # Regla 2: Un usuario no puede dejar más de una reseña activa por libro
        if user and user.is_authenticated and book:
            duplicate_qs = Review.objects.filter(
                user=user,
                book=book,
                deleted_at__isnull=True
            )
            if self.instance:
                duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)

            if duplicate_qs.exists():
                raise serializers.ValidationError({
                    "book": "El usuario ya tiene una reseña activa para este libro."
                })

        return attrs
        
# ==========================================
# FAVORITOS
# ==========================================

        
class FavoriteSerializer(serializers.ModelSerializer):
    user_detail = UserSummarySerializer(source="user", read_only=True)
    book_detail = BookSimpleSerializer(source="book", read_only=True)

    class Meta:
        model = User.favorites.through
        fields = [
            "id",
            "user",
            "user_detail",
            "book",
            "book_detail",
        ]
        read_only_fields = ["id", "user"]

    def create(self, validated_data):
        favorite, _ = self.Meta.model.objects.get_or_create(**validated_data)
        return favorite