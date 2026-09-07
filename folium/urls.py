"""
Rutas principales de folium.
Acá se conectan las distintas partes del sistema con sus direcciones web.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Panel de administración de Django (http://localhost:8000/admin/)
    path('admin/', admin.site.urls),
    path('admin/', admin.site.urls),

    # Browsable API de DRF. Una herramienta buenísima. Les super recomiendo aprender a usar esto
    # Busquen algún tutorial de "Browsable API DRF"
    path("api-auth/", include("rest_framework.urls")) 

    # Pantalla de inicio de sesión visual para probar la API desde el navegador
    path('api-auth/', include('rest_framework.urls')),
]
