from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def seed_subscription_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model("folium_api", "SubscriptionPlan")
    catalog = {
        "PLUS": {
            "name": "Folium Acervo Plus",
            "badge_text": "",
            "description": "Capacidad ampliada y herramientas de catalogación ágil para modernizar tu biblioteca comunitaria o escolar.",
            "monthly_price": Decimal("14990.00"),
            "annual_monthly_equivalent": Decimal("11990.00"),
            "currency_id": "ARS",
            "max_books": 5000,
            "max_items": 15000,
            "max_librarians": 3,
            "has_mass_importer": True,
            "has_ai_curator": False,
            "has_priority_support": False,
        },
        "PRO": {
            "name": "Folium Patrimonio Pro",
            "badge_text": "Incluye Curador IA Avanzado & Acervo Ilimitado",
            "description": "Acceso mejorado e ilimitado a funciones avanzadas de preservación, analítica y automatización para impulsar tu institución.",
            "monthly_price": Decimal("34990.00"),
            "annual_monthly_equivalent": Decimal("27990.00"),
            "currency_id": "ARS",
            "max_books": 0,
            "max_items": 0,
            "max_librarians": 15,
            "has_mass_importer": True,
            "has_ai_curator": True,
            "has_priority_support": True,
        },
    }

    for code, values in catalog.items():
        SubscriptionPlan.objects.update_or_create(
            code=code,
            defaults={
                "name": values["name"],
                "badge_text": values["badge_text"],
                "description": values["description"],
                "monthly_price": values["monthly_price"],
                "annual_monthly_equivalent": values["annual_monthly_equivalent"],
                "currency_id": values["currency_id"],
                "max_books": values["max_books"],
                "max_items": values["max_items"],
                "max_librarians": values["max_librarians"],
                "has_mass_importer": values["has_mass_importer"],
                "has_ai_curator": values["has_ai_curator"],
                "has_priority_support": values["has_priority_support"],
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("folium_api", "0009_performance_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(choices=[("FREE", "Folium Comunidad (Sin Cargo)"), ("PLUS", "Folium Acervo Plus"), ("PRO", "Folium Patrimonio Pro")], max_length=20, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("badge_text", models.CharField(blank=True, default="", max_length=120)),
                ("description", models.TextField(blank=True)),
                ("monthly_price", models.DecimalField(decimal_places=2, default="0.00", max_digits=12)),
                ("annual_monthly_equivalent", models.DecimalField(decimal_places=2, default="0.00", max_digits=12, help_text="Precio mensual equivalente al contratar facturación anual (ej. 20% off).")),
                ("currency_id", models.CharField(default="ARS", max_length=10)),
                ("max_books", models.PositiveIntegerField(default=250, help_text="Cantidad máxima de títulos únicos en el catálogo (0 = ilimitado).")),
                ("max_items", models.PositiveIntegerField(default=500, help_text="Cantidad máxima de ejemplares físicos en inventario (0 = ilimitado).")),
                ("max_librarians", models.PositiveSmallIntegerField(default=1, help_text="Cantidad de cuentas con rol BIBLIOTECARIO permitidas.")),
                ("has_mass_importer", models.BooleanField(default=False, help_text="Habilita el importador masivo de catálogos Excel/CSV.")),
                ("has_ai_curator", models.BooleanField(default=False, help_text="Habilita recomendaciones avanzadas y curaduría asistida por IA.")),
                ("has_priority_support", models.BooleanField(default=False)),
                ("mp_preapproval_plan_id", models.CharField(blank=True, max_length=100, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["monthly_price"],
                "verbose_name": "Plan de Suscripción",
                "verbose_name_plural": "Planes de Suscripción",
            },
        ),
        migrations.CreateModel(
            name="LibrarySubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("organization_name", models.CharField(help_text="Nombre de la Biblioteca, Archivo o Institución.", max_length=150)),
                ("tax_id", models.CharField(blank=True, default="", help_text="CUIT / CUIL / RUT institucional para facturación.", max_length=20)),
                ("payer_email", models.EmailField(max_length=254)),
                ("billing_cycle", models.CharField(choices=[("MONTHLY", "Mensual"), ("ANNUAL", "Anual")], default="MONTHLY", max_length=15)),
                ("status", models.CharField(choices=[("PENDING", "Pendiente de Pago"), ("ACTIVE", "Activa"), ("PAST_DUE", "Pago demorado / En reintento"), ("CANCELLED", "Cancelada"), ("EXPIRED", "Expirada")], default="PENDING", max_length=20)),
                ("mp_preference_id", models.CharField(blank=True, db_index=True, max_length=120, null=True)),
                ("mp_preapproval_id", models.CharField(blank=True, db_index=True, max_length=120, null=True)),
                ("external_reference", models.CharField(db_index=True, max_length=100, unique=True)),
                ("current_period_start", models.DateTimeField(blank=True, null=True)),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("cancel_at_period_end", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="folium_api.subscriptionplan")),
                ("user", models.ForeignKey(help_text="Usuario administrador o bibliotecario titular de la suscripción.", on_delete=django.db.models.deletion.PROTECT, related_name="library_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Suscripción de Biblioteca",
                "verbose_name_plural": "Suscripciones de Bibliotecas",
            },
        ),
        migrations.CreateModel(
            name="PaymentTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mp_payment_id", models.CharField(db_index=True, help_text="ID único del pago en MercadoPago (garantiza idempotencia).", max_length=100, unique=True)),
                ("external_reference", models.CharField(db_index=True, max_length=100)),
                ("status", models.CharField(choices=[("approved", "Aprobado"), ("pending", "Pendiente"), ("authorized", "Autorizado"), ("in_process", "En proceso de revisión"), ("in_mediation", "En mediación"), ("rejected", "Rechazado"), ("cancelled", "Cancelado"), ("refunded", "Reembolsado"), ("charged_back", "Contracargo")], default="pending", max_length=30)),
                ("status_detail", models.CharField(blank=True, default="", max_length=100)),
                ("transaction_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency_id", models.CharField(default="ARS", max_length=10)),
                ("payment_method_id", models.CharField(blank=True, default="", max_length=50)),
                ("payment_type_id", models.CharField(blank=True, default="", max_length=50)),
                ("payer_email", models.EmailField(blank=True, default="", max_length=254)),
                ("raw_response", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subscription", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payments", to="folium_api.librarysubscription")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Transacción de Pago",
                "verbose_name_plural": "Transacciones de Pago",
            },
        ),
        migrations.CreateModel(
            name="WebhookEventLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_id", models.CharField(blank=True, db_index=True, default="", max_length=120)),
                ("event_type", models.CharField(blank=True, default="", max_length=60)),
                ("data_id", models.CharField(blank=True, db_index=True, default="", max_length=100)),
                ("signature_valid", models.BooleanField(default=False)),
                ("processed", models.BooleanField(default=False)),
                ("error_message", models.TextField(blank=True, default="")),
                ("raw_headers", models.JSONField(blank=True, default=dict)),
                ("raw_payload", models.JSONField(blank=True, default=dict)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-received_at"],
                "verbose_name": "Log de Webhook MercadoPago",
                "verbose_name_plural": "Logs de Webhooks MercadoPago",
            },
        ),
        migrations.RunPython(seed_subscription_plans, migrations.RunPython.noop),
    ]
