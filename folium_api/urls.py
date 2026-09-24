from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Nombre para identificar las rutas de esta app
app_name = 'folium_api'

# El router genera automáticamente las rutas estándar para guardar, ver, editar y borrar datos
router = DefaultRouter()

# Ejemplo de cómo registrar un modelo en el router (crea URLs como /api/v1/productos/):
# router.register(r'productos', views.ProductoViewSet, basename='producto')

# Registro del ViewSet de Items
router.register(r'items', views.ItemViewSet, basename='item')


# Registro del ViewSet de Prestamos
router.register(r'loan', views.LoanViewSet, basename='loan')

# Registro del ViewSet de Book
router.register(r'book', views.BookViewSet, basename='book')

# Registro del ViewSet de Author
router.register(r'author', views.AuthorViewSet, basename='author')

# Registro del ViewSet de Author
router.register(r'genre', views.GenreViewSet, basename='genre')

urlpatterns = [
    # Incluye las rutas automáticas creadas por el router
    path('', include(router.urls)),
    
    # Rutas personalizadas basadas en vistas clase o funciones (ejemplo):
    # path('contacto/', views.ContactView.as_view(), name='contacto'),
]




