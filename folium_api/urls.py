from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Nombre para identificar las rutas de esta app
app_name = 'folium_api'

# El router genera automáticamente las rutas estándar para guardar, ver, editar y borrar datos
router = DefaultRouter()

# Ejemplo de cómo registrar un modelo en el router (crea URLs como /api/v1/productos/):
# router.register(r'productos', views.ProductoViewSet, basename='producto')

urlpatterns = [
    # Incluye las rutas automáticas creadas por el router
    path('', include(router.urls)),
    
    # Rutas personalizadas basadas en vistas clase o funciones (ejemplo):
    # path('contacto/', views.ContactView.as_view(), name='contacto'),
]
