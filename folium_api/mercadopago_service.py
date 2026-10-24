import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from decimal import Decimal

logger = logging.getLogger(__name__)

# ==============================================================================
# CATÁLOGO OFICIAL DE PLANES INSTITUCIONALES (FUENTE DE VERDAD DEL SERVIDOR)
# ==============================================================================
# IMPORTANTE: Jamás aceptar montos enviados desde el navegador. El backend
# determina el precio únicamente a partir del `plan_code` y `billing_cycle`.

LIBRARY_PLANS_CATALOG = {
    "PLUS": {
        "code": "PLUS",
        "name": "Folium Acervo Plus",
        "superscript": "1",
        "badge_text": "",
        "is_featured": False,
        "subtitle_prefix": "Obtén ",
        "subtitle_highlight": "capacidad ampliada",
        "subtitle_suffix": " y herramientas de catalogación ágil para modernizar tu biblioteca comunitaria o escolar.",
        "monthly_price": Decimal("14990.00"),
        "annual_monthly_equivalent": Decimal("11990.00"),
        "annual_total_price": Decimal("143880.00"),
        "currency_id": "ARS",
        "usd_reference": "14.99",
        "usage_multiplier_note": "Obtén 5 veces más capacidad de acervo que con la versión sin cargo",
        "cta_label": "Comenzar",
        "includes_heading": "Todo lo que incluye la modalidad sin cargo, además de lo siguiente:",
        "limits": {
            "max_books": 5000,
            "max_items": 15000,
            "max_librarians": 3,
            "has_mass_importer": True,
            "has_ai_curator": False,
            "has_priority_support": False,
        },
        "feature_groups": [
            {
                "category": "Gestión de Archivo e Inventario",
                "items": [
                    "Hasta 5.000 títulos únicos y 15.000 ejemplares físicos trazables",
                    "Importador masivo de catálogos por Excel (.xlsx) y CSV con simulación previa",
                    "Hasta 3 cuentas de Bibliotecario con panel de circulación y préstamos",
                    "Control de ubicaciones físicas por sala, pasillo y estantería",
                ],
            },
            {
                "category": "Comunidad y Experiencia Lectora",
                "items": [
                    "Acceso al Asistente Curador Folium estándar para consultas de socios",
                    "Sistema de reservas online con bloqueo automático de ejemplares²",
                    "Reportes mensuales de préstamos activos, morosidad y devoluciones",
                ],
            },
        ],
    },
    "PRO": {
        "code": "PRO",
        "name": "Folium Patrimonio Pro",
        "superscript": "1",
        "badge_text": "Incluye Curador IA Avanzado & Acervo Ilimitado",
        "is_featured": True,
        "subtitle_prefix": "Obtén ",
        "subtitle_highlight": "acceso mejorado e ilimitado",
        "subtitle_suffix": " a funciones avanzadas de preservación, analítica y automatización para impulsar tu institución.",
        "monthly_price": Decimal("34990.00"),
        "annual_monthly_equivalent": Decimal("27990.00"),
        "annual_total_price": Decimal("335880.00"),
        "currency_id": "ARS",
        "usd_reference": "34.99",
        "usage_multiplier_note": "Catálogo ilimitado y 10 veces más velocidad operativa institucional",
        "cta_label": "Comenzar",
        "includes_heading": "Todo lo que incluye Folium Acervo Plus, además de lo siguiente:",
        "limits": {
            "max_books": 0,  # 0 = Ilimitado
            "max_items": 0,  # 0 = Ilimitado
            "max_librarians": 15,
            "has_mass_importer": True,
            "has_ai_curator": True,
            "has_priority_support": True,
        },
        "feature_groups": [
            {
                "category": "Suite Patrimonial & IA de Biblioteca",
                "items": [
                    "Acceso al Curador IA Pro con recomendaciones semánticas personalizadas",
                    "Obras, volúmenes y ejemplares físicos ilimitados en múltiples sedes²",
                    "Hasta 15 cuentas de Bibliotecario y Administrador con auditoría de cambios",
                    "Importación y exportación masiva sin límite de filas ni tamaño de lote",
                ],
            },
            {
                "category": "Soporte Institucional y Prioridad",
                "items": [
                    "Atención prioritaria y acompañamiento técnico en la migración inicial",
                    "Estadísticas históricas de lectura, rotación de fondo y reseñas verificadas",
                    "Personalización de reglas de préstamo y plazos por tipo de colección",
                ],
            },
        ],
    },
}


class MercadoPagoWebhookSecurityError(Exception):
    """Excepción lanzada cuando la firma HMAC-SHA256 del Webhook es inválida."""
    pass


class MercadoPagoServiceError(Exception):
    """Excepción lanzada ante errores de comunicación con la API de MercadoPago."""
    pass


class MercadoPagoService:
    """
    Servicio centralizado para operar con MercadoPago:
    1. Checkout Pro / Wallet Brick (Preferencias de pago único mensual/anual).
    2. Suscripciones Recurrentes (PreApproval para débito automático).
    3. Verificación criptográfica de Webhooks (x-signature HMAC-SHA256).
    4. Consulta directa de pagos (Server-to-Server verification).
    """

    API_BASE_URL = "https://api.mercadopago.com"

    def __init__(self):
        self.access_token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
        self.public_key = os.environ.get("MP_PUBLIC_KEY", "").strip()
        self.webhook_secret = os.environ.get("MP_WEBHOOK_SECRET", "").strip()
        self.frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
        self.backend_url = os.environ.get("BACKEND_PUBLIC_URL", "http://localhost:8080").rstrip("/")

    @property
    def is_configured(self) -> bool:
        """Indica si existe un Access Token real o de prueba de MercadoPago."""
        return bool(self.access_token)

    def _mp_request(self, method: str, endpoint: str, payload: dict = None, idempotency_key: str = None) -> dict:
        """
        Ejecuta una petición HTTPS hacia la API de MercadoPago.
        Intenta usar el SDK oficial `mercadopago` si está instalado, o bien realiza
        la llamada HTTPS directa con cabeceras de seguridad e idempotencia (`X-Idempotency-Key`).
        """
        url = f"{self.API_BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Folium-Library-Platform/1.0",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode("utf-8", errors="replace")
            logger.error("MercadoPago API HTTP Error %s en %s: %s", http_err.code, endpoint, err_body)
            raise MercadoPagoServiceError(
                f"MercadoPago rechazó la solicitud ({http_err.code}): {err_body}"
            ) from http_err
        except urllib.error.URLError as url_err:
            logger.error("MercadoPago Connection Error en %s: %s", endpoint, str(url_err))
            raise MercadoPagoServiceError(
                "No fue posible establecer conexión con los servidores de MercadoPago."
            ) from url_err

    def create_checkout_preference(
        self,
        *,
        plan_code: str,
        billing_cycle: str,
        user_id: int,
        payer_email: str,
        organization_name: str,
        tax_id: str = "",
    ) -> dict:
        """
        Crea una Preferencia de Pago (Checkout Pro / Wallet Brick).
        El precio se obtiene exclusivamente del catálogo del servidor.
        """
        plan = LIBRARY_PLANS_CATALOG.get(plan_code)
        if not plan:
            raise ValueError(f"El plan '{plan_code}' no existe en el catálogo oficial.")

        cycle = "ANNUAL" if str(billing_cycle).upper() == "ANNUAL" else "MONTHLY"
        unit_price = float(
            plan["annual_total_price"] if cycle == "ANNUAL" else plan["monthly_price"]
        )
        cycle_label = "Suscripción Anual (12 meses - 20% Off)" if cycle == "ANNUAL" else "Suscripción Mensual"

        external_reference = f"FOLIUM-{plan_code}-{cycle}-U{user_id}-{uuid.uuid4().hex[:10].upper()}"
        idempotency_key = str(uuid.uuid4())

        preference_payload = {
            "items": [
                {
                    "id": f"FOLIUM-{plan_code}-{cycle}",
                    "title": f"{plan['name']} — {cycle_label}",
                    "description": f"Licencia institucional para {organization_name}",
                    "category_id": "services",
                    "quantity": 1,
                    "currency_id": plan["currency_id"],
                    "unit_price": unit_price,
                }
            ],
            "payer": {
                "email": payer_email,
                "name": organization_name[:80],
            },
            "back_urls": {
                "success": f"{self.frontend_url}/pricing?payment_status=approved&plan={plan_code}&cycle={cycle}",
                "failure": f"{self.frontend_url}/pricing?payment_status=rejected&plan={plan_code}&cycle={cycle}",
                "pending": f"{self.frontend_url}/pricing?payment_status=pending&plan={plan_code}&cycle={cycle}",
            },
            "auto_return": "approved",
            "external_reference": external_reference,
            "statement_descriptor": "FOLIUM BIBLIO",
            "binary_mode": False,
            "metadata": {
                "plan_code": plan_code,
                "billing_cycle": cycle,
                "user_id": user_id,
                "organization_name": organization_name,
                "tax_id": tax_id,
            },
        }

        # Si el backend tiene una URL pública HTTPS configurada, añadimos notification_url
        if self.backend_url.startswith("https://"):
            preference_payload["notification_url"] = (
                f"{self.backend_url}/api/v1/billing/webhook/mercadopago/"
            )

        # Si las credenciales reales están configuradas, llamamos a MercadoPago
        if self.is_configured:
            mp_resp = self._mp_request(
                "POST",
                "/checkout/preferences",
                payload=preference_payload,
                idempotency_key=idempotency_key,
            )
            return {
                "mode": "LIVE_OR_SANDBOX_API",
                "preference_id": mp_resp.get("id"),
                "init_point": mp_resp.get("init_point"),
                "sandbox_init_point": mp_resp.get("sandbox_init_point"),
                "external_reference": external_reference,
                "amount": unit_price,
                "currency_id": plan["currency_id"],
                "plan_name": plan["name"],
                "billing_cycle": cycle,
                "public_key": self.public_key,
            }

        # Modo Simulación / Desarrollo Local (cuando aún no se cargó MP_ACCESS_TOKEN en .env)
        simulated_pref_id = f"SANDBOX-PREF-{uuid.uuid4().hex[:14].upper()}"
        return {
            "mode": "LOCAL_SIMULATION",
            "preference_id": simulated_pref_id,
            "init_point": (
                f"{self.frontend_url}/pricing?payment_status=approved"
                f"&plan={plan_code}&cycle={cycle}&external_reference={external_reference}"
                f"&payment_id=SIM-{uuid.uuid4().hex[:8].upper()}&simulated=true"
            ),
            "sandbox_init_point": (
                f"{self.frontend_url}/pricing?payment_status=approved"
                f"&plan={plan_code}&cycle={cycle}&external_reference={external_reference}"
                f"&payment_id=SIM-{uuid.uuid4().hex[:8].upper()}&simulated=true"
            ),
            "external_reference": external_reference,
            "amount": unit_price,
            "currency_id": plan["currency_id"],
            "plan_name": plan["name"],
            "billing_cycle": cycle,
            "public_key": self.public_key or "TEST-00000000-0000-0000-0000-000000000000",
            "simulation_notice": (
                "Modo simulación activo: Configura MP_ACCESS_TOKEN en el archivo .env "
                "del backend para redirigir al checkout real de MercadoPago."
            ),
        }

    def create_recurring_subscription(
        self,
        *,
        plan_code: str,
        billing_cycle: str,
        user_id: int,
        payer_email: str,
        organization_name: str,
    ) -> dict:
        """
        Crea una suscripción de débito automático mediante la API `/preapproval` de MercadoPago.
        Ideal para cobro recurrente mensual o anual automático.
        """
        plan = LIBRARY_PLANS_CATALOG.get(plan_code)
        if not plan:
            raise ValueError(f"El plan '{plan_code}' no existe en el catálogo oficial.")

        cycle = "ANNUAL" if str(billing_cycle).upper() == "ANNUAL" else "MONTHLY"
        frequency = 12 if cycle == "ANNUAL" else 1
        transaction_amount = float(
            plan["annual_total_price"] if cycle == "ANNUAL" else plan["monthly_price"]
        )
        external_reference = f"FOLIUM-SUB-{plan_code}-{cycle}-U{user_id}-{uuid.uuid4().hex[:8].upper()}"

        preapproval_payload = {
            "reason": f"{plan['name']} ({'Anual' if cycle == 'ANNUAL' else 'Mensual'}) — {organization_name}",
            "external_reference": external_reference,
            "payer_email": payer_email,
            "auto_recurring": {
                "frequency": frequency,
                "frequency_type": "months",
                "transaction_amount": transaction_amount,
                "currency_id": plan["currency_id"],
            },
            "back_url": f"{self.frontend_url}/pricing?payment_status=authorized&plan={plan_code}&cycle={cycle}",
            "status": "pending",
        }

        if self.is_configured:
            mp_resp = self._mp_request(
                "POST",
                "/preapproval",
                payload=preapproval_payload,
                idempotency_key=str(uuid.uuid4()),
            )
            return {
                "mode": "LIVE_OR_SANDBOX_API",
                "preapproval_id": mp_resp.get("id"),
                "init_point": mp_resp.get("init_point"),
                "external_reference": external_reference,
                "amount": transaction_amount,
                "currency_id": plan["currency_id"],
            }

        simulated_sub_id = f"SANDBOX-SUB-{uuid.uuid4().hex[:12].upper()}"
        return {
            "mode": "LOCAL_SIMULATION",
            "preapproval_id": simulated_sub_id,
            "init_point": (
                f"{self.frontend_url}/pricing?payment_status=authorized"
                f"&plan={plan_code}&cycle={cycle}&preapproval_id={simulated_sub_id}&simulated=true"
            ),
            "external_reference": external_reference,
            "amount": transaction_amount,
            "currency_id": plan["currency_id"],
        }

    def fetch_payment_details(self, payment_id: str) -> dict:
        """
        Consulta directamente en los servidores de MercadoPago el estado real de un pago.
        NUNCA se debe dar por válido un pago únicamente por los parámetros GET de retorno.
        """
        if not self.is_configured:
            return {
                "id": payment_id,
                "status": "approved",
                "status_detail": "accredited_simulation",
                "currency_id": "ARS",
                "simulated": True,
            }
        return self._mp_request("GET", f"/v1/payments/{payment_id}")

    def verify_webhook_signature(
        self,
        *,
        x_signature: str,
        x_request_id: str,
        data_id: str,
        tolerance_seconds: int = 300,
    ) -> bool:
        """
        Verifica criptográficamente la firma HMAC-SHA256 enviada por MercadoPago en el header `x-signature`.

        Formato del manifiesto oficial de MercadoPago:
            id:[data.id_url_lowercase];request-id:[x-request-id_header];ts:[ts_header];
        """
        if not self.webhook_secret:
            raise MercadoPagoWebhookSecurityError(
                "MP_WEBHOOK_SECRET no está configurado en el servidor."
            )

        if not x_signature or not x_request_id or not data_id:
            raise MercadoPagoWebhookSecurityError(
                "Faltan cabeceras criptográficas obligatorias (x-signature, x-request-id o data.id)."
            )

        # 1. Extraer ts y v1 del header x-signature (ej: "ts=1704908010,v1=618c85345...")
        parts = {}
        for piece in x_signature.split(","):
            if "=" in piece:
                k, v = piece.strip().split("=", 1)
                parts[k.strip()] = v.strip()

        ts_str = parts.get("ts")
        v1_hash = parts.get("v1")

        if not ts_str or not v1_hash:
            raise MercadoPagoWebhookSecurityError(
                "El formato de la cabecera x-signature es inválido (faltan campos ts o v1)."
            )

        # 2. Verificar ventana temporal para mitigar ataques de Replay
        try:
            ts_int = int(ts_str)
        except ValueError as err:
            raise MercadoPagoWebhookSecurityError("El timestamp (ts) de la firma no es numérico.") from err

        now_ts = int(time.time())
        if tolerance_seconds > 0 and abs(now_ts - ts_int) > tolerance_seconds:
            raise MercadoPagoWebhookSecurityError(
                f"La firma del webhook expiró (diferencia: {abs(now_ts - ts_int)}s > {tolerance_seconds}s)."
            )

        # 3. Construir el template oficial: si data_id es alfanumérico, debe ir en minúsculas
        normalized_data_id = str(data_id).lower()
        manifest = f"id:{normalized_data_id};request-id:{x_request_id};ts:{ts_str};"

        # 4. Calcular HMAC-SHA256 y comparar en tiempo constante
        computed_hmac = hmac.new(
            self.webhook_secret.encode("utf-8"),
            msg=manifest.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(computed_hmac, v1_hash):
            raise MercadoPagoWebhookSecurityError(
                "La firma HMAC-SHA256 no coincide con el payload recibido."
            )

        return True
