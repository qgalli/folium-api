"""
Rutas principales del proyecto Folium.
Acá se conectan las distintas partes del sistema con sus direcciones web.
"""

from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Panel de administración de Django (http://localhost:8000/admin/)
    path('admin/', admin.site.urls),
    
    # Rutas de la API (todas las direcciones de la API empiezan con /api/v1/)
    path('api/v1/', include('folium_api.urls')),
    
    # Pantalla de inicio de sesión visual para probar la API desde el navegador
    path('api-auth/', include('rest_framework.urls')),

    # Autenticación JWT
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

# Sirve los archivos de /media (portadas, etc.) durante desarrollo.
# En producción esto lo debería servir el proxy (nginx, S3, etc.), no Django.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)