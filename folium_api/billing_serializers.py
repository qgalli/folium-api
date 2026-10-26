import re
from rest_framework import serializers
from .mercadopago_service import LIBRARY_PLANS_CATALOG


class CreateCheckoutPreferenceSerializer(serializers.Serializer):
    """
    Valida los datos enviados por el frontend para iniciar el proceso de pago
    con MercadoPago Checkout Pro o Wallet Brick.
    """
    plan_code = serializers.ChoiceField(
        choices=[(k, v["name"]) for k, v in LIBRARY_PLANS_CATALOG.items()],
        error_messages={
            "invalid_choice": "El plan seleccionado no es válido. Opciones permitidas: PLUS, PRO."
        },
    )
    billing_cycle = serializers.ChoiceField(
        choices=[("MONTHLY", "Mensual"), ("ANNUAL", "Anual")],
        default="MONTHLY",
    )
    organization_name = serializers.CharField(
        max_length=150,
        min_length=3,
        trim_whitespace=True,
        error_messages={
            "blank": "Debes ingresar el nombre de la biblioteca o institución.",
            "min_length": "El nombre de la institución debe tener al menos 3 caracteres.",
        },
    )
    tax_id = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        default="",
    )
    payer_email = serializers.EmailField(
        required=False,
        allow_blank=True,
        error_messages={
            "invalid": "Ingresa un correo electrónico válido para el comprobante de facturación."
        },
    )
    checkout_mode = serializers.ChoiceField(
        choices=[("PREFERENCE", "Pago por período (Checkout Pro)"), ("SUBSCRIPTION", "Débito automático recurrente")],
        default="PREFERENCE",
    )

    def validate_tax_id(self, value):
        cleaned = re.sub(r"[\s-]", "", value or "")
        if cleaned and not re.match(r"^\d{8,13}$", cleaned):
            raise serializers.ValidationError(
                "El CUIT / CUIL / RUT debe contener entre 8 y 13 dígitos numéricos."
            )
        return cleaned
