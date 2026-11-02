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

# Registro del ViewSet de Genre
router.register(r'genre', views.GenreViewSet, basename='genre')

# Registro del ViewSet de Editorial
router.register(r'editorial', views.EditorialViewSet, basename='editorial')

# Registro del ViewSet de Favoritos
router.register(r'favorites', views.FavoriteViewSet, basename='favorite')

# Registro del ViewSet de Reservas (Lector)
router.register(r'reservations', views.ReservationViewSet, basename='reservation')

# Registro del ViewSet de Reseñas (Lector)
router.register(r'reviews', views.ReviewViewSet, basename='review')

# Registro del ViewSet de Usuarios (Bibliotecarios / Admin)
router.register(r'user', views.UserViewSet, basename='user')
router.register(r'users', views.UserViewSet, basename='users')

urlpatterns = [
    # Ruta pública de autoregistro
    path('register/', views.ReaderRegistrationView.as_view(), name='reader-register'),

    # Perfil del usuario autenticado (Lector / Bibliotecario / Admin)
    path('me/', views.UserProfileView.as_view(), name='user-profile'),

    # Endpoints públicos de libros (no requieren login)
    path('random/', views.RandomBookView.as_view(), name='random-book'),
    path('recommendation/', views.BookRecommendationView.as_view(), name='book-recommendation'),
    path('recommendations/', views.BookRecommendationView.as_view(), name='book-recommendations'),

    # Módulo de importador masivo de catálogos (Fase 1: Excel / CSV)
    path('importer/', include('folium_api.importer_urls')),

    # Módulo de planes institucionales y pasarela de pago MercadoPago
    path('billing/', include('folium_api.billing_urls')),

    # Incluye las rutas automáticas creadas por el router
    path('', include(router.urls)),
    
    # Rutas personalizadas basadas en vistas clase o funciones (ejemplo):
    # path('contacto/', views.ContactView.as_view(), name='contacto'),
]
