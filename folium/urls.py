"""
Rutas principales del proyecto Folium.
Acá se conectan las distintas partes del sistema con sus direcciones web.
"""

from django.contrib import admin
from django.urls import include, path, re_path
from rest_framework_simplejwt.views import TokenRefreshView
from folium_api.views import (
    FoliumTokenObtainPairView,
    RandomBookView,
    BookRecommendationView,
)
from folium_api.media_views import serve_optimized_media

urlpatterns = [
    # Panel de administración de Django (http://localhost:8000/admin/)
    path('admin/', admin.site.urls),
    
    # Rutas de la API (todas las direcciones de la API empiezan con /api/v1/)
    path('api/v1/', include('folium_api.urls')),
    
    # Pantalla de inicio de sesión visual para probar la API desde el navegador
    path('api-auth/', include('rest_framework.urls')),

    # Autenticación JWT
    path('api/v1/token/', FoliumTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Rutas públicas directas a nivel raíz
    path('random/', RandomBookView.as_view(), name='root-random'),
    path('recommendation/', BookRecommendationView.as_view(), name='root-recommendation'),
    path('recommendations/', BookRecommendationView.as_view(), name='root-recommendations'),

    # Entrega optimizada de archivos /media/ con cabeceras Edge CDN y fallback a WebP
    re_path(r'^media/(?P<path>.*)$', serve_optimized_media, name='serve-media'),
]
