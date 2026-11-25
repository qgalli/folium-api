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

from django.conf import settings

logger = logging.getLogger(__name__)

# ==============================================================================
# CATÁLOGO OFICIAL DE PLANES INSTITUCIONALES (FUENTE DE VERDAD DEL SERVIDOR)
# ==============================================================================
# IMPORTANTE: Jamás aceptar montos enviados desde el navegador. El backend
# determina el precio únicamente a partir del `plan_code` y `billing_cycle`.

LIBRARY_PLANS_CATALOG = {
    "BASIC": {
        "code": "BASIC",
        "name": "Folium Gestión",
        "superscript": "1",
        "badge_text": "Solo Gestión de Biblioteca & Inventario",
        "is_featured": False,
        "subtitle_prefix": "Ideal para instituciones que desean ",
        "subtitle_highlight": "ordenar su catálogo y mostrador",
        "subtitle_suffix": " sin habilitar un portal web público a los usuarios.",
        "monthly_price": Decimal("247000.00"),
        "annual_monthly_equivalent": Decimal("205800.00"),
        "annual_total_price": Decimal("2470000.00"),
        "currency_id": "ARS",
        "usd_reference": "190.00",
        "annual_usd_reference": "158.33",
        "usage_multiplier_note": "Incluye 50 GB de almacenamiento AWS S3 y 250 GB de tráfico CloudFront",
        "cta_label": "Contratar Plan Gestión",
        "includes_heading": "Funcionalidades de administración interna incluidas:",
        "limits": {
            "max_books": 10000,
            "max_items": 25000,
            "max_librarians": 3,
            "has_reader_portal": False,
            "has_coverflow_3d": False,
            "has_mass_importer": True,
            "has_ai_curator": False,
            "has_priority_support": False,
            "s3_storage_gb": 50,
            "cloudfront_bandwidth_gb": 250,
        },
        "feature_groups": [
            {
                "category": "Administración y Circulación Interna",
                "items": [
                    "Panel exclusivo de bibliotecario con préstamos y devoluciones de mostrador",
                    "Jerarquía ontológica dual: Obra (Book) y Ejemplares físicos (BookItem)",
                    "Control de signatura topográfica exacta (Sala, Pasillo y Estante)",
                    "Hasta 3 cuentas simultáneas de personal bibliotecario y catalogador",
                    "Importador ágil de fondos bibliográficos mediante planillas Excel (.xlsx) y CSV",
                ],
            },
            {
                "category": "Límites de Infraestructura Cloud en AWS",
                "items": [
                    "50 GB de almacenamiento seguro en Amazon S3 para portadas y respaldos",
                    "250 GB / mes de transferencia de datos en AWS CloudFront",
                    "Base de datos PostgreSQL con respaldo diario automatizado",
                    "Hasta 10.000 títulos únicos y 25.000 ejemplares físicos con código de barras",
                ],
            },
        ],
    },
    "PRO": {
        "code": "PRO",
        "name": "Folium Integral",
        "superscript": "1",
        "badge_text": "Recomendado • Estado Actual Completo (Usuarios + Biblioteca)",
        "is_featured": True,
        "subtitle_prefix": "Nuestra solución integral que ",
        "subtitle_highlight": "conecta a los bibliotecarios con toda la comunidad",
        "subtitle_suffix": " mediante catálogo 3D, reservas 24/7 y motor MARC 21.",
        "monthly_price": Decimal("455000.00"),
        "annual_monthly_equivalent": Decimal("379100.00"),
        "annual_total_price": Decimal("4550000.00"),
        "currency_id": "ARS",
        "usd_reference": "350.00",
        "annual_usd_reference": "291.66",
        "usage_multiplier_note": "Incluye 250 GB de almacenamiento AWS S3 y 1 TB de tráfico mensual acelerado",
        "cta_label": "Comenzar con Plan Integral",
        "includes_heading": "Todo lo del Plan Básico, más el portal completo de usuarios:",
        "limits": {
            "max_books": 50000,
            "max_items": 120000,
            "max_librarians": 10,
            "has_reader_portal": True,
            "has_coverflow_3d": True,
            "has_mass_importer": True,
            "has_ai_curator": False,
            "has_priority_support": True,
            "s3_storage_gb": 250,
            "cloudfront_bandwidth_gb": 1000,
        },
        "feature_groups": [
            {
                "category": "Portal del Lector & OPAC 3D",
                "items": [
                    "Catálogo público con Carrusel 3D CoverFlow y física de resorte",
                    "Portal autogestionado del socio con credencial digital institucional por DNI",
                    "Módulo de Reservas Online 24/7 y semáforo automático de vencimientos",
                    "Buscador reactivo con filtro por facetas y stock en sala en tiempo real",
                    "Socios lectores y estudiantes activos ilimitados",
                ],
            },
            {
                "category": "Rigor Internacional MARC 21 & Circulación",
                "items": [
                    "Ingesta nativa de archivos MARC 21 (.mrc ISO 2709), MARCXML y BibTeX",
                    "Simulación Dry-Run previa para verificar consistencia antes de persistir",
                    "Notificaciones automáticas por correo electrónico con Celery y Redis",
                    "Hasta 10 puestos de bibliotecarios y administradores con auditoría forense",
                ],
            },
            {
                "category": "Límites de Infraestructura Cloud en AWS",
                "items": [
                    "250 GB de almacenamiento en Amazon S3 para activos en alta definición",
                    "1.000 GB (1 TB) / mes de transferencia en AWS CloudFront",
                    "Snapshots automáticos de base de datos cada 12 horas con retención de 15 días",
                ],
            },
        ],
    },
    "PREMIUM": {
        "code": "PREMIUM",
        "name": "Folium Nexus AI",
        "superscript": "1",
        "badge_text": "Suite de Vanguardia • Tomito AI Bot + Multi-Sede + API",
        "is_featured": False,
        "subtitle_prefix": "Para instituciones y consorcios que exigen ",
        "subtitle_highlight": "Inteligencia Artificial generativa y multisede",
        "subtitle_suffix": " con integraciones académicas y resiliencia de misión crítica.",
        "monthly_price": Decimal("767000.00"),
        "annual_monthly_equivalent": Decimal("639100.00"),
        "annual_total_price": Decimal("7670000.00"),
        "currency_id": "ARS",
        "usd_reference": "590.00",
        "annual_usd_reference": "491.66",
        "usage_multiplier_note": "Incluye 1 TB de almacenamiento AWS S3, 5 TB de tráfico CloudFront y clúster Multi-AZ",
        "cta_label": "Solicitar Plan Nexus AI",
        "includes_heading": "Todo lo del Plan Pro, más tecnologías de vanguardia:",
        "limits": {
            "max_books": 0,
            "max_items": 0,
            "max_librarians": 0,
            "has_reader_portal": True,
            "has_coverflow_3d": True,
            "has_mass_importer": True,
            "has_ai_curator": True,
            "has_priority_support": True,
            "s3_storage_gb": 1000,
            "cloudfront_bandwidth_gb": 5000,
        },
        "feature_groups": [
            {
                "category": "Conserje Inteligente Tomito AI (RAG Generativo)",
                "items": [
                    "Asistente conversacional Tomito AI entrenado sobre el catálogo propio",
                    "Búsqueda semántica en lenguaje natural y recomendaciones personalizadas",
                    "Hasta 25.000 consultas mensuales de alumnos y socios asistidas por IA",
                    "Respuestas instantáneas de stock, estantería y reglamento de sala",
                ],
            },
            {
                "category": "Consorcios Multi-Sede & Conectividad",
                "items": [
                    "Gestión multi-campus y multi-sucursal con catálogo colectivo centralizado",
                    "Préstamo y circulación interbibliotecaria entre diferentes sedes",
                    "API REST completa y Webhooks para integración con LMS (Moodle, Canvas, Classroom)",
                    "Obras, ejemplares físicos y cuentas de operadores ilimitados",
                ],
            },
            {
                "category": "Infraestructura Empresarial Dedicada en AWS",
                "items": [
                    "1.000 GB (1 TB) de almacenamiento en Amazon S3 ampliable sin tope",
                    "5.000 GB (5 TB) / mes de transferencia con aceleración perimetral",
                    "Clúster PostgreSQL Multi-AZ de alta disponibilidad con réplica de lectura",
                    "SLA del 99.9% garantizado por contrato y canal de soporte prioritario 24/7",
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
        self.access_token = (
            os.environ.get("MP_ACCESS_TOKEN")
            or os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
            or ""
        ).strip()
        self.public_key = (
            os.environ.get("MP_PUBLIC_KEY")
            or os.environ.get("MERCADOPAGO_PUBLIC_KEY")
            or ""
        ).strip()
        self.webhook_secret = (
            os.environ.get("MP_WEBHOOK_SECRET")
            or os.environ.get("MERCADOPAGO_WEBHOOK_SECRET")
            or ""
        ).strip()
        self.frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
        self.backend_url = (
            os.environ.get("BACKEND_PUBLIC_URL")
            or os.environ.get("BACKEND_URL")
            or "http://localhost:8080"
        ).rstrip("/")

        # Configuración del SDK oficial si la librería mercadopago está instalada
        self.sdk = None
        if self.access_token:
            try:
                import mercadopago
                self.sdk = mercadopago.SDK(self.access_token)
            except ImportError:
                self.sdk = None

    @property
    def is_configured(self) -> bool:
        """Indica si existe un Access Token real o de prueba de MercadoPago."""
        return bool(self.access_token)

    def _mp_request(self, method: str, endpoint: str, payload: dict = None, idempotency_key: str = None) -> dict:
        """
        Ejecuta una petición HTTPS hacia la API de MercadoPago.
        Si el SDK oficial `mercadopago` está disponible, delega la creación de preferencias
        o llamadas a través de él; de lo contrario realiza la llamada HTTPS directa
        con cabeceras de seguridad e idempotencia (`X-Idempotency-Key`).
        """
        # Si disponemos del SDK oficial y es la creación de preferencia
        if self.sdk and method == "POST" and endpoint == "/checkout/preferences" and payload:
            try:
                from mercadopago.config.request_options import RequestOptions

                request_options = None
                if idempotency_key:
                    request_options = RequestOptions(
                        custom_headers={"X-Idempotency-Key": idempotency_key}
                    )
                pref_res = self.sdk.preference().create(
                    payload, request_options=request_options
                )
                status_code = pref_res.get("status")
                response_data = pref_res.get("response", {})
                if status_code in (200, 201):
                    return response_data
                raise MercadoPagoServiceError(
                    f"MercadoPago SDK rechazó la solicitud ({status_code}): {response_data}"
                )
            except Exception as sdk_err:
                if isinstance(sdk_err, MercadoPagoServiceError):
                    raise sdk_err
                logger.warning("Fallo en llamada via SDK mercadopago (%s), reintentando HTTP directo", str(sdk_err))

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

        # auto_return solo es valido si el frontend es una URL publica y alcanzable
        # desde los servidores de MercadoPago (HTTPS). En localhost/desarrollo se
        # omite para evitar el error 400:
        # "auto_return invalid. back_url.success must be defined".
        if self.frontend_url.startswith("https://"):
            preference_payload["auto_return"] = "approved"

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
        self._ensure_simulation_allowed()
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

        self._ensure_simulation_allowed()
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

    def _ensure_simulation_allowed(self) -> None:
        if not settings.DEBUG:
            raise MercadoPagoServiceError(
                "La pasarela MercadoPago no está configurada en el servidor (falta MP_ACCESS_TOKEN)."
            )

    def fetch_payment_details(self, payment_id: str) -> dict:
        """
        Consulta directamente en los servidores de MercadoPago el estado real de un pago.
        NUNCA se debe dar por válido un pago únicamente por los parámetros GET de retorno.
        """
        if not self.is_configured:
            self._ensure_simulation_allowed()
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
