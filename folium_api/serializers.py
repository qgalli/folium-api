import re
from datetime import datetime
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db.models import Avg, Q
from .models import * # Importamos todos los modelos del archivo `models.py` (que está en este mismo directorio)
from .permissions import is_admin

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


def _validate_user_password(password, attrs, instance=None):
    """Ejecuta AUTH_PASSWORD_VALIDATORS considerando los atributos del usuario."""
    if not password:
        return
    candidate = User(
        username=attrs.get("username", getattr(instance, "username", "")),
        first_name=attrs.get("first_name", getattr(instance, "first_name", "")),
        last_name=attrs.get("last_name", getattr(instance, "last_name", "")),
        email=attrs.get("email", getattr(instance, "email", "")),
    )
    try:
        validate_password(password, user=candidate)
    except DjangoValidationError as error:
        raise serializers.ValidationError({"password": list(error.messages)}) from error


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_new_password"]:
            raise serializers.ValidationError({
                "confirm_new_password": "Las contraseñas nuevas no coinciden."
            })

        try:
            validate_password(attrs["new_password"], user=self.context["request"].user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": error.messages}) from error

        return attrs


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

    def validate_name(self, value):
        str_val = re.sub(r"\s+", " ", str(value or "").strip())
        if not str_val:
            raise serializers.ValidationError("El nombre de la editorial no puede estar vacío.")
        if str_val.isdigit():
            raise serializers.ValidationError("El nombre de la editorial no puede consistir únicamente de números.")

        queryset = Editorial.objects.filter(name__iexact=str_val)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Ya existe una editorial registrada con este nombre.")

        return str_val


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        min_length=8,
    )
    full_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "dni",
            "first_name",
            "last_name",
            "full_name",
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

    def get_full_name(self, obj):
        name = obj.get_full_name()
        return name if name and name.strip() else obj.username

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

    def validate_rol(self, value):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor and actor.is_authenticated and not is_admin(actor):
            current_rol = getattr(self.instance, "rol", None)
            if value == User.Rol.ADMIN or (value != User.Rol.USER and value != current_rol):
                raise serializers.ValidationError("Solo un administrador puede asignar ese rol.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if actor and actor.is_authenticated and not is_admin(actor) and self.instance:
            if self.instance.rol == User.Rol.ADMIN or self.instance.is_superuser:
                raise serializers.ValidationError(
                    "Solo un administrador puede gestionar cuentas administrativas."
                )
            if actor.pk != self.instance.pk:
                if "password" in attrs:
                    raise serializers.ValidationError({
                        "password": "No puedes cambiar la contraseña de otro usuario."
                    })
                if "is_active" in attrs and attrs["is_active"] != self.instance.is_active:
                    raise serializers.ValidationError({
                        "is_active": "Solo un administrador puede cambiar el estado activo de otro usuario."
                    })
        if "password" in attrs:
            _validate_user_password(attrs.get("password"), attrs, instance=self.instance)
        return attrs

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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        _validate_user_password(attrs.get("password"), attrs)
        return attrs

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

    def validate(self, attrs):
        book = attrs.get("book", getattr(self.instance, "book", None))
        if book is not None and book.deleted_at is not None:
            raise serializers.ValidationError({
                "book": "No se puede asignar un ejemplar a un libro eliminado."
            })

        new_status = attrs.get("status")
        if self.instance is None:
            if new_status in (Item.Status.LOANED, Item.Status.RESERVED):
                raise serializers.ValidationError({
                    "status": f"No se puede crear un ejemplar directamente en estado '{new_status}'."
                })
            return attrs

        old_status = self.instance.status
        target_status = new_status if new_status is not None else old_status
        if target_status == old_status:
            return attrs

        if target_status in (Item.Status.LOANED, Item.Status.RESERVED):
            raise serializers.ValidationError({
                "status": f"El estado '{target_status}' solo puede gestionarse desde préstamos o reservas."
            })

        if (
            old_status in (Item.Status.DAMAGED, Item.Status.LOST)
            and target_status == Item.Status.AVAILABLE
        ):
            raise serializers.ValidationError({
                "status": "Un ejemplar dañado o perdido solo puede volver a estar disponible mediante la acción de revisión (mark-reviewed)."
            })

        if self.instance.loans.filter(returned_at__isnull=True).exists():
            raise serializers.ValidationError({
                "status": "No se puede cambiar el estado de un ejemplar con un préstamo activo sin devolver."
            })

        if (
            self.instance.reservations.filter(
                status=Reservation.StatusReservation.PENDING,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
            .exists()
        ):
            raise serializers.ValidationError({
                "status": "No se puede cambiar el estado de un ejemplar con una reserva pendiente vigente."
            })

        return attrs


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


class BookOptionSerializer(serializers.ModelSerializer):
    """
    Serializador super liviano para selects / autocompletados (LoadBookForm, ItemForm).
    """
    class Meta:
        model = Book
        fields = [
            "id",
            "title",
            "isbn",
        ]


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


def _get_book_items(obj):
    if hasattr(obj, "prefetched_items"):
        return obj.prefetched_items
    return list(obj.items.all())


def _get_available_book_items(obj):
    if hasattr(obj, "prefetched_available_items"):
        return obj.prefetched_available_items
    return [item for item in _get_book_items(obj) if item.status == Item.Status.AVAILABLE]


def _get_unassigned_pending_reservations_count(obj):
    if hasattr(obj, "prefetched_pending_reservations"):
        return len(obj.prefetched_pending_reservations)
    return sum(
        1
        for r in obj.reservations.all()
        if r.status == Reservation.StatusReservation.PENDING and r.item_id is None
    )


class BookAvailableOptionSerializer(serializers.ModelSerializer):
    """
    Serializador de libros que tienen ejemplares físicos disponibles,
    con el detalle de sus ítems para selección directa en el mostrador de préstamos.
    """
    editorial = EditorialSummarySerializer(read_only=True)
    authors = AuthorSummarySerializer(many=True, read_only=True)
    genres = GenreSummarySerializer(many=True, read_only=True)
    available_items = serializers.SerializerMethodField()
    available_count = serializers.SerializerMethodField()

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
            "available_items",
            "available_count",
        ]

    def get_available_items(self, obj):
        return ItemSummarySerializer(_get_available_book_items(obj), many=True).data

    def get_available_count(self, obj):
        return len(_get_available_book_items(obj))


class EditorialPrimaryKeyOrNameField(serializers.PrimaryKeyRelatedField):
    """
    Permite recibir tanto el ID numérico de una Editorial existente como su nombre en texto
    (buscando case-insensitive o creándola si no existe).
    """
    def to_internal_value(self, data):
        if isinstance(data, Editorial):
            return data
        if isinstance(data, int) or (isinstance(data, str) and data.strip().isdigit()):
            try:
                return super().to_internal_value(int(str(data).strip()))
            except serializers.ValidationError:
                if isinstance(data, int):
                    raise
        if isinstance(data, str):
            clean_name = re.sub(r"\s+", " ", data.strip())
            if not clean_name:
                raise serializers.ValidationError("El nombre de la editorial no puede estar vacío.")
            if len(clean_name) > 150:
                raise serializers.ValidationError("El nombre de la editorial admite hasta 150 caracteres.")
            existing = Editorial.objects.filter(name__iexact=clean_name).first()
            if existing:
                return existing
            return Editorial.objects.create(name=clean_name)
        return super().to_internal_value(data)

class BookWriteSerializer(serializers.ModelSerializer):
    editorial = EditorialPrimaryKeyOrNameField(
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
        extra_kwargs = {
            "isbn": {
                # Desactivamos el UniqueValidator automático de DRF sobre la tabla completa
                # para que validate_isbn verifique unicidad solo contra libros activos,
                # permitiendo reactivar libros dados de baja (soft deleted).
                "validators": [],
            }
        }

    def validate_isbn(self, value):
        if not value:
            return None
        clean_isbn = re.sub(r'[\s-]', '', str(value))
        if not clean_isbn.isdigit():
            raise serializers.ValidationError("El ISBN solo puede contener números (y guiones).")
        if len(clean_isbn) not in (10, 13):
            raise serializers.ValidationError("El ISBN debe tener exactamente 10 o 13 dígitos.")

        # Validar unicidad únicamente contra libros activos
        active_books = Book.objects.filter(isbn=clean_isbn, deleted_at__isnull=True)
        if self.instance:
            active_books = active_books.exclude(pk=self.instance.pk)
        if active_books.exists():
            raise serializers.ValidationError("Ya existe un libro activo registrado con este ISBN.")

        return clean_isbn

    def validate_publication_year(self, value):
        current_year = datetime.now().year
        if value > current_year:
            raise serializers.ValidationError(f"El año de publicación no puede ser posterior al año actual ({current_year}).")
        if value < 868:
            raise serializers.ValidationError("El año de publicación no puede ser anterior al año 868 d.C.")
        return value

    def create(self, validated_data):
        isbn = validated_data.get('isbn')
        # Si el libro ya existía pero estaba eliminado lógicamente (soft deleted),
        # se reactiva actualizando sus datos en lugar de intentar un nuevo INSERT (que fallaría por UNIQUE de BD).
        if isbn:
            deleted_book = Book.objects.filter(isbn=isbn, deleted_at__isnull=False).first()
            if deleted_book:
                authors = validated_data.pop('authors', None)
                genres = validated_data.pop('genres', None)
                for attr, val in validated_data.items():
                    setattr(deleted_book, attr, val)
                deleted_book.deleted_at = None
                deleted_book.save()
                if authors is not None:
                    deleted_book.authors.set(authors)
                if genres is not None:
                    deleted_book.genres.set(genres)
                return deleted_book

        return super().create(validated_data)
    

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
    total_items = serializers.SerializerMethodField()
    available_items = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()

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
            "total_items",
            "available_items",
            "is_available",
        ]

    def get_total_items(self, obj):
        return len(_get_book_items(obj))

    def get_available_items(self, obj):
        return max(
            0,
            len(_get_available_book_items(obj)) - _get_unassigned_pending_reservations_count(obj),
        )

    def get_is_available(self, obj):
        return self.get_available_items(obj) > 0


class ItemReadSerializer(serializers.ModelSerializer):
    """
    Serializador de lectura para Item (usado en GET list y retrieve).
    Anida la información del libro (título, autores, géneros, portada, isbn)
    para que el catálogo de ejemplares no requiera peticiones extras.
    """
    book = BookListSerializer(read_only=True)
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
        return len(_get_book_items(obj))

    def get_available_items(self, obj):
        return max(
            0,
            len(_get_available_book_items(obj)) - _get_unassigned_pending_reservations_count(obj),
        )



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
        authors = list(obj.authors.all())
        return ", ".join(f"{a.name} {a.last_name}".strip() for a in authors) or None

    def get_category(self, obj):
        genres = list(obj.genres.all())
        return genres[0].name if genres else None

    def get_rating(self, obj):
        if hasattr(obj, "avg_rating"):
            return round(float(avg), 2) if (avg := obj.avg_rating) is not None else None
        active_reviews = obj.reviews.filter(deleted_at__isnull=True)
        avg_aggregate = active_reviews.aggregate(avg=Avg("rating"))["avg"]
        return round(float(avg_aggregate), 2) if avg_aggregate is not None else None

    def get_total_items(self, obj):
        return len(_get_book_items(obj))

    def get_available_items(self, obj):
        return max(
            0,
            len(_get_available_book_items(obj)) - _get_unassigned_pending_reservations_count(obj),
        )


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
        extra_kwargs = {
            "loaned_at": {"required": False},
            "due_at": {"required": False},
        }

    def _assert_item_available_for_loan(self, item, user, instance=None):
        active_loan = Loan.objects.filter(item=item, returned_at__isnull=True)
        if instance is not None:
            active_loan = active_loan.exclude(pk=instance.pk)
        if active_loan.exists():
            raise serializers.ValidationError({
                "item": "El ejemplar seleccionado ya se encuentra prestado o no está disponible."
            })

        is_new_or_different_item = instance is None or instance.item_id != item.id
        if is_new_or_different_item and item.status != Item.Status.AVAILABLE:
            has_matching_reservation = (
                item.status == Item.Status.RESERVED
                and user is not None
                and Reservation.objects.filter(
                    item=item,
                    user=user,
                    status=Reservation.StatusReservation.PENDING,
                    expires_at__gt=timezone.now(),
                ).exists()
            )
            if not has_matching_reservation:
                raise serializers.ValidationError({
                    "item": "El ejemplar seleccionado ya se encuentra prestado o no está disponible."
                })

    def validate(self, attrs):
        from datetime import timedelta
        # Asignar valores por defecto para préstamos nuevos
        if not attrs.get("loaned_at") and (not self.instance or not getattr(self.instance, "loaned_at", None)):
            attrs["loaned_at"] = timezone.now()
        if not attrs.get("due_at") and (not self.instance or not getattr(self.instance, "due_at", None)):
            attrs["due_at"] = attrs["loaned_at"] + timedelta(days=14)

        loaned_at = attrs.get("loaned_at", getattr(self.instance, "loaned_at", None))
        due_at = attrs.get("due_at", getattr(self.instance, "due_at", None))
        returned_at = attrs.get("returned_at", getattr(self.instance, "returned_at", None))
        item = attrs.get("item", getattr(self.instance, "item", None))
        user = attrs.get("user", getattr(self.instance, "user", None))

        if self.instance is not None and self.instance.returned_at is not None:
            if "returned_at" in attrs and attrs["returned_at"] is None:
                raise serializers.ValidationError({
                    "returned_at": "No se puede reabrir un préstamo ya devuelto."
                })
            if item is not None and item.pk != self.instance.item_id:
                raise serializers.ValidationError({
                    "item": "No se puede cambiar el ejemplar de un préstamo ya devuelto."
                })

        # 1. Validaciones de fechas
        if due_at and loaned_at and due_at <= loaned_at:
            raise serializers.ValidationError({"due_at": "La fecha de vencimiento debe ser posterior a la fecha de inicio del préstamo."})

        if returned_at and loaned_at and returned_at < loaned_at:
            raise serializers.ValidationError({"returned_at": "La fecha de devolución no puede ser anterior a la fecha de inicio del préstamo."})

        # 2. Validación de disponibilidad del ejemplar
        if item:
            if (self.instance is None or item.pk != self.instance.item_id) and item.book.deleted_at is not None:
                raise serializers.ValidationError({
                    "item": "No se puede prestar un ejemplar de un libro eliminado."
                })
            if returned_at is None:
                self._assert_item_available_for_loan(item, user, instance=self.instance)

        return attrs

    def create(self, validated_data):
        with transaction.atomic():
            target_item = validated_data["item"]
            locked_item = Item.objects.select_for_update().get(pk=target_item.pk)
            validated_data["item"] = locked_item

            if validated_data.get("returned_at") is None:
                self._assert_item_available_for_loan(
                    locked_item,
                    validated_data.get("user"),
                    instance=None,
                )

            reservation = Reservation.objects.select_for_update().filter(
                item=locked_item,
                user=validated_data.get("user"),
                status=Reservation.StatusReservation.PENDING,
                expires_at__gt=timezone.now(),
            ).first()

            try:
                loan = super().create(validated_data)
            except IntegrityError:
                raise serializers.ValidationError({
                    "item": "El ejemplar seleccionado ya se encuentra prestado o no está disponible."
                })

            if loan.returned_at is None:
                locked_item.status = Item.Status.LOANED
                locked_item.save(update_fields=["status", "updated_at"])

            if reservation:
                reservation.status = Reservation.StatusReservation.COMPLETED
                reservation.save(update_fields=["status", "updated_at"])
            return loan

    def update(self, instance, validated_data):
        with transaction.atomic():
            locked_loan = Loan.objects.select_for_update().get(pk=instance.pk)
            was_returned = locked_loan.returned_at is not None
            candidate_item = validated_data.get("item", locked_loan.item)
            item_ids = sorted({locked_loan.item_id, candidate_item.pk})
            locked_items = {
                obj.pk: obj
                for obj in Item.objects.select_for_update().filter(pk__in=item_ids).order_by("pk")
            }
            previous_item = locked_items[locked_loan.item_id]
            target_item = locked_items[candidate_item.pk]
            if "item" in validated_data:
                validated_data["item"] = target_item

            new_returned_at = validated_data.get("returned_at", locked_loan.returned_at)
            if was_returned and new_returned_at is None:
                raise serializers.ValidationError({
                    "returned_at": "No se puede reabrir un préstamo ya devuelto."
                })

            if new_returned_at is None:
                self._assert_item_available_for_loan(
                    target_item,
                    validated_data.get("user", locked_loan.user),
                    instance=locked_loan,
                )

            reservation = None
            if not was_returned and new_returned_at is None and target_item.pk != previous_item.pk:
                reservation = Reservation.objects.select_for_update().filter(
                    item=target_item,
                    user=validated_data.get("user", locked_loan.user),
                    status=Reservation.StatusReservation.PENDING,
                    expires_at__gt=timezone.now(),
                ).first()

            try:
                loan = super().update(locked_loan, validated_data)
            except IntegrityError:
                raise serializers.ValidationError({
                    "item": "El ejemplar seleccionado ya se encuentra prestado o no está disponible."
                })

            # Si cambiaron el ejemplar físico, liberamos el anterior solo si figuraba prestado
            if previous_item.pk != loan.item_id and previous_item.status == Item.Status.LOANED:
                previous_item.status = Item.Status.AVAILABLE
                previous_item.save(update_fields=["status", "updated_at"])

            # Si ya tiene fecha de devolución, vuelve a AVAILABLE salvo que esté DAMAGED/LOST
            current_item = locked_items[loan.item_id]
            if loan.returned_at is not None:
                if current_item.status not in (Item.Status.DAMAGED, Item.Status.LOST):
                    current_item.status = Item.Status.AVAILABLE
                    current_item.save(update_fields=["status", "updated_at"])
            else:
                if current_item.status != Item.Status.LOANED:
                    current_item.status = Item.Status.LOANED
                    current_item.save(update_fields=["status", "updated_at"])

            if reservation:
                reservation.status = Reservation.StatusReservation.COMPLETED
                reservation.save(update_fields=["status", "updated_at"])

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

    def validate_book(self, book):
        if book.deleted_at is not None:
            raise serializers.ValidationError("No se puede agregar a favoritos un libro eliminado.")
        return book

    def create(self, validated_data):
        favorite, _ = self.Meta.model.objects.get_or_create(**validated_data)
        return favorite