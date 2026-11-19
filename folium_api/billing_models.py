from decimal import Decimal
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class SubscriptionPlan(models.Model):
    """
    Catálogo de planes institucionales para bibliotecas en Folium.
    NOTA CRÍTICA DE SEGURIDAD: Los precios y límites SIEMPRE se leen desde
    este modelo o configuración del servidor, jamás desde el payload del cliente.
    """
    class PlanCode(models.TextChoices):
        FREE = "FREE", "Folium Comunidad (Sin Cargo)"
        BASIC = "BASIC", "Folium Gestión"
        PRO = "PRO", "Folium Integral"
        PREMIUM = "PREMIUM", "Folium Nexus AI"

    code = models.CharField(
        max_length=20,
        choices=PlanCode.choices,
        unique=True,
    )
    name = models.CharField(max_length=100)
    badge_text = models.CharField(max_length=120, blank=True, default="")
    description = models.TextField(blank=True)

    # Precios expresados en moneda local (ARS por defecto para MercadoPago Argentina)
    monthly_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    annual_monthly_equivalent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Precio mensual equivalente al contratar facturación anual (ej. 20% off).",
    )
    currency_id = models.CharField(max_length=10, default="ARS")

    # Límites operativos del plan (Feature Gating)
    max_books = models.PositiveIntegerField(
        default=250,
        help_text="Cantidad máxima de títulos únicos en el catálogo (0 = ilimitado).",
    )
    max_items = models.PositiveIntegerField(
        default=500,
        help_text="Cantidad máxima de ejemplares físicos en inventario (0 = ilimitado).",
    )
    max_librarians = models.PositiveSmallIntegerField(
        default=1,
        help_text="Cantidad de cuentas con rol BIBLIOTECARIO permitidas.",
    )
    has_mass_importer = models.BooleanField(
        default=False,
        help_text="Habilita el importador masivo de catálogos Excel/CSV.",
    )
    has_ai_curator = models.BooleanField(
        default=False,
        help_text="Habilita recomendaciones avanzadas y curaduría asistida por IA.",
    )
    has_priority_support = models.BooleanField(default=False)

    # ID de plan preconfigurado en MercadoPago (PreApproval Plan) si se usa débito automático
    mp_preapproval_plan_id = models.CharField(max_length=100, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["monthly_price"]
        verbose_name = "Plan de Suscripción"
        verbose_name_plural = "Planes de Suscripción"

    def clean(self):
        errors = {}
        if self.monthly_price < Decimal("0.00"):
            errors["monthly_price"] = "El precio mensual no puede ser negativo."
        if self.annual_monthly_equivalent < Decimal("0.00"):
            errors["annual_monthly_equivalent"] = "El precio anualizado no puede ser negativo."
        if errors:
            raise ValidationError(errors)

    def get_Checkout_amount(self, billing_cycle="MONTHLY"):
        """
        Calcula el monto exacto a cobrar según el ciclo de facturación.
        """
        if billing_cycle == "ANNUAL":
            return (self.annual_monthly_equivalent * Decimal("12")).quantize(Decimal("0.01"))
        return self.monthly_price.quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.name} ({self.monthly_price} {self.currency_id}/mes)"


class LibrarySubscription(models.Model):
    """
    Representa la suscripción activa o histórica de una biblioteca/institución.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente de Pago"
        ACTIVE = "ACTIVE", "Activa"
        PAST_DUE = "PAST_DUE", "Pago demorado / En reintento"
        CANCELLED = "CANCELLED", "Cancelada"
        EXPIRED = "EXPIRED", "Expirada"

    class BillingCycle(models.TextChoices):
        MONTHLY = "MONTHLY", "Mensual"
        ANNUAL = "ANNUAL", "Anual"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="library_subscriptions",
        null=True,
        blank=True,
        help_text="Usuario administrador o bibliotecario titular de la suscripción.",
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
    )

    organization_name = models.CharField(
        max_length=150,
        help_text="Nombre de la Biblioteca, Archivo o Institución.",
    )
    tax_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="CUIT / CUIL / RUT institucional para facturación.",
    )
    payer_email = models.EmailField()

    billing_cycle = models.CharField(
        max_length=15,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Identificadores de trazabilidad en MercadoPago
    mp_preference_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    mp_preapproval_id = models.CharField(max_length=120, blank=True, null=True, db_index=True)
    external_reference = models.CharField(max_length=100, unique=True, db_index=True)

    current_period_start = models.DateTimeField(blank=True, null=True)
    current_period_end = models.DateTimeField(blank=True, null=True)
    cancel_at_period_end = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Suscripción de Biblioteca"
        verbose_name_plural = "Suscripciones de Bibliotecas"

    def activate_period(self):
        """
        Activa la suscripción y extiende la vigencia según el ciclo contratado.
        """
        now = timezone.now()
        days = 365 if self.billing_cycle == self.BillingCycle.ANNUAL else 30
        self.status = self.Status.ACTIVE
        self.current_period_start = now
        self.current_period_end = now + timezone.timedelta(days=days)
        self.save(update_fields=["status", "current_period_start", "current_period_end", "updated_at"])

    def __str__(self):
        return f"{self.organization_name} - {self.plan.name} [{self.status}]"


class PaymentTransaction(models.Model):
    """
    Registro auditable e inmutable de cada transacción informada por MercadoPago.
    Garantiza idempotencia mediante `mp_payment_id` único.
    """
    class PaymentStatus(models.TextChoices):
        APPROVED = "approved", "Aprobado"
        PENDING = "pending", "Pendiente"
        AUTHORIZED = "authorized", "Autorizado"
        IN_PROCESS = "in_process", "En proceso de revisión"
        IN_MEDIATION = "in_mediation", "En mediación"
        REJECTED = "rejected", "Rechazado"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Reembolsado"
        CHARGED_BACK = "charged_back", "Contracargo"

    subscription = models.ForeignKey(
        LibrarySubscription,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    mp_payment_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="ID único del pago en MercadoPago (garantiza idempotencia).",
    )
    external_reference = models.CharField(max_length=100, db_index=True)
    status = models.CharField(
        max_length=30,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    status_detail = models.CharField(max_length=100, blank=True, default="")
    transaction_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency_id = models.CharField(max_length=10, default="ARS")
    payment_method_id = models.CharField(max_length=50, blank=True, default="")
    payment_type_id = models.CharField(max_length=50, blank=True, default="")
    payer_email = models.EmailField(blank=True, default="")

    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Transacción de Pago"
        verbose_name_plural = "Transacciones de Pago"

    def __str__(self):
        return f"MP Payment #{self.mp_payment_id} - {self.transaction_amount} {self.currency_id} ({self.status})"


class WebhookEventLog(models.Model):
    """
    Bitácora de auditoría para todas las notificaciones entrantes del Webhook de MercadoPago.
    """
    request_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=60, blank=True, default="")
    data_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default="")
    raw_headers = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Log de Webhook MercadoPago"
        verbose_name_plural = "Logs de Webhooks MercadoPago"

    def __str__(self):
        return f"Webhook [{self.event_type}] ID={self.data_id} Valid={self.signature_valid}"
