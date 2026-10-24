import logging
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .billing_serializers import CreateCheckoutPreferenceSerializer
from .mercadopago_service import (
    LIBRARY_PLANS_CATALOG,
    MercadoPagoService,
    MercadoPagoServiceError,
    MercadoPagoWebhookSecurityError,
)

logger = logging.getLogger(__name__)


class BillingPlansListView(APIView):
    """
    GET /api/v1/billing/plans/
    Endpoint público que devuelve el catálogo oficial de planes para bibliotecas,
    sus precios en ARS/USD, límites operativos y configuración pública de MercadoPago.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        mp_service = MercadoPagoService()
        plans_list = []

        for code, plan_data in LIBRARY_PLANS_CATALOG.items():
            plans_list.append({
                "code": plan_data["code"],
                "name": plan_data["name"],
                "superscript": plan_data["superscript"],
                "badge_text": plan_data["badge_text"],
                "is_featured": plan_data["is_featured"],
                "subtitle_prefix": plan_data["subtitle_prefix"],
                "subtitle_highlight": plan_data["subtitle_highlight"],
                "subtitle_suffix": plan_data["subtitle_suffix"],
                "monthly_price": str(plan_data["monthly_price"]),
                "annual_monthly_equivalent": str(plan_data["annual_monthly_equivalent"]),
                "annual_total_price": str(plan_data["annual_total_price"]),
                "currency_id": plan_data["currency_id"],
                "usd_reference": plan_data["usd_reference"],
                "usage_multiplier_note": plan_data["usage_multiplier_note"],
                "cta_label": plan_data["cta_label"],
                "includes_heading": plan_data["includes_heading"],
                "limits": plan_data["limits"],
                "feature_groups": plan_data["feature_groups"],
            })

        return Response(
            {
                "plans": plans_list,
                "gateway": {
                    "provider": "mercadopago",
                    "is_live_configured": mp_service.is_configured,
                    "public_key": mp_service.public_key or None,
                    "supported_methods": [
                        "Tarjetas de crédito y débito (Visa, Mastercard, Cabal, Amex)",
                        "Dinero en cuenta de MercadoPago",
                        "Transferencia inmediata / DEBIN",
                    ],
                },
            },
            status=status.HTTP_200_OK,
        )


class CreateCheckoutPreferenceView(APIView):
    """
    POST /api/v1/billing/checkout/
    Genera una Preferencia de Pago (Checkout Pro / Wallet Brick) o una Suscripción
    Recurrente (PreApproval) en MercadoPago tomando siempre los montos del servidor.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = CreateCheckoutPreferenceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        plan_code = validated["plan_code"]
        billing_cycle = validated["billing_cycle"]
        organization_name = validated["organization_name"]
        tax_id = validated.get("tax_id", "")
        checkout_mode = validated.get("checkout_mode", "PREFERENCE")

        # Determinamos el usuario y su email
        user = request.user if (request.user and request.user.is_authenticated) else None
        user_id = user.id if user else 0
        payer_email = (
            validated.get("payer_email")
            or (getattr(user, "email", None) if user else None)
            or "administracion@biblioteca-folium.org"
        )

        mp_service = MercadoPagoService()

        try:
            if checkout_mode == "SUBSCRIPTION":
                checkout_data = mp_service.create_recurring_subscription(
                    plan_code=plan_code,
                    billing_cycle=billing_cycle,
                    user_id=user_id,
                    payer_email=payer_email,
                    organization_name=organization_name,
                )
            else:
                checkout_data = mp_service.create_checkout_preference(
                    plan_code=plan_code,
                    billing_cycle=billing_cycle,
                    user_id=user_id,
                    payer_email=payer_email,
                    organization_name=organization_name,
                    tax_id=tax_id,
                )

            return Response(
                {
                    "success": True,
                    "checkout": checkout_data,
                },
                status=status.HTTP_201_CREATED,
            )
        except MercadoPagoServiceError as mp_err:
            return Response(
                {"detail": str(mp_err)},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as err:
            logger.exception("Error inesperado creando checkout en MercadoPago: %s", str(err))
            return Response(
                {"detail": "No se pudo inicializar la pasarela de pago. Intenta nuevamente."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyPaymentStatusView(APIView):
    """
    GET /api/v1/billing/payment-status/?payment_id=...&external_reference=...
    Verifica directamente con MercadoPago el estado real de un pago al regresar de las back_urls.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        payment_id = request.query_params.get("payment_id") or request.query_params.get("collection_id")
        external_reference = request.query_params.get("external_reference", "")
        status_param = request.query_params.get("payment_status") or request.query_params.get("status", "")

        if not payment_id:
            return Response(
                {
                    "verified": False,
                    "status": status_param or "unknown",
                    "external_reference": external_reference,
                    "detail": "No se proporcionó un identificador de pago para verificar.",
                },
                status=status.HTTP_200_OK,
            )

        mp_service = MercadoPagoService()
        try:
            payment_info = mp_service.fetch_payment_details(payment_id)
            real_status = payment_info.get("status", status_param)

            return Response(
                {
                    "verified": real_status in ("approved", "authorized"),
                    "payment_id": str(payment_id),
                    "status": real_status,
                    "status_detail": payment_info.get("status_detail", ""),
                    "external_reference": payment_info.get("external_reference") or external_reference,
                    "simulated": bool(payment_info.get("simulated", False)),
                },
                status=status.HTTP_200_OK,
            )
        except MercadoPagoServiceError as err:
            return Response(
                {"detail": str(err)},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class MercadoPagoWebhookView(APIView):
    """
    POST /api/v1/billing/webhook/mercadopago/
    Receptor oficial de Webhooks de MercadoPago (Server-to-Server).
    Implementa:
    1. Validación criptográfica HMAC-SHA256 del header `x-signature`.
    2. Prevención de ataques de Replay validando el timestamp `ts`.
    3. Consulta cruzada (GET /v1/payments/{id}) para confirmar el estado real en MercadoPago.
    4. Procesamiento idempotente.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # Exento de JWT ya que la autenticación es por firma HMAC

    def post(self, request, *args, **kwargs):
        x_signature = request.headers.get("x-signature", "")
        x_request_id = request.headers.get("x-request-id", "")

        # MercadoPago envía data.id por query params (?data.id=1234&type=payment) y/o en el body JSON
        payload = request.data if isinstance(request.data, dict) else {}
        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        data_id = (
            request.query_params.get("data.id")
            or data_obj.get("id")
            or request.query_params.get("id")
            or ""
        )
        event_type = (
            request.query_params.get("type")
            or payload.get("type")
            or request.query_params.get("topic")
            or "unknown"
        )

        mp_service = MercadoPagoService()

        # 1. Validar firma criptográfica si MP_WEBHOOK_SECRET está configurado
        if mp_service.webhook_secret:
            try:
                mp_service.verify_webhook_signature(
                    x_signature=x_signature,
                    x_request_id=x_request_id,
                    data_id=str(data_id),
                )
            except MercadoPagoWebhookSecurityError as sec_err:
                logger.warning(
                    "Webhook MercadoPago rechazado por firma inválida (request_id=%s, data_id=%s): %s",
                    x_request_id,
                    data_id,
                    str(sec_err),
                )
                return Response(
                    {"detail": "Firma de webhook inválida."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        # 2. Si el evento es un pago, consultar los detalles directamente en la API de MercadoPago
        if event_type == "payment" and data_id:
            try:
                payment_details = mp_service.fetch_payment_details(str(data_id))
                payment_status = payment_details.get("status")
                ext_ref = payment_details.get("external_reference", "")

                logger.info(
                    "Webhook MercadoPago procesado con éxito: payment_id=%s status=%s ref=%s",
                    data_id,
                    payment_status,
                    ext_ref,
                )
            except MercadoPagoServiceError as err:
                logger.error("Error consultando pago %s en Webhook: %s", data_id, str(err))
                return Response(
                    {"detail": "Error temporal al verificar el pago."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response({"received": True, "event_type": event_type}, status=status.HTTP_200_OK)
