import logging

from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.views import exception_handler

logger = logging.getLogger("folium_api.auth")

UNIFORM_AUTH_ERROR_DETAIL = "Credenciales inválidas o sesión no autorizada."


def custom_exception_handler(exc, context):
    """Uniforma los errores 401 de DRF/JWT y registra el motivo real en servidor."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)) or response.status_code == 401:
        view = context.get("view")
        request = context.get("request")
        logger.warning(
            "Authentication failure (%s) on %s %s [view=%s]: %s",
            type(exc).__name__,
            getattr(request, "method", "-"),
            getattr(request, "path", "-"),
            view.__class__.__name__ if view is not None else "-",
            exc,
        )
        response.data = {"detail": UNIFORM_AUTH_ERROR_DETAIL}

    return response
