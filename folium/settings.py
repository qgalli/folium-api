"""
Configuración de Django para el proyecto Folium.

Generado con 'django-admin startproject' usando Django 6.1.

Para más información sobre este archivo, ver:
https://docs.djangoproject.com/en/6.1/topics/settings/

Para la lista completa de configuraciones y sus valores, ver:
https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Ruta base del proyecto (directorio raíz donde está manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent


# ─── Seguridad ────────────────────────────────────────────────────────────────
# La SECRET_KEY se lee desde la variable de entorno definida en .env
# NUNCA hardcodear este valor en el código
SECRET_KEY = os.environ.get('SECRET_KEY')

# DEBUG se lee desde el entorno; en producción debe ser False
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Hosts permitidos: en desarrollo se acepta '*' o localhost; en producción se lee desde el entorno
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    hosts_env = os.environ.get('ALLOWED_HOSTS', '')
    ALLOWED_HOSTS = [h.strip() for h in hosts_env.split(',') if h.strip()] if hosts_env else [
        'localhost',
        '127.0.0.1',
        '54.160.130.29',
        '.vercel.app',
    ]

# Le dice a Django que use nuestro modelo de usuario personalizado en lugar del que viene por defecto
AUTH_USER_MODEL = 'folium_api.User'

# ─── Aplicaciones instaladas ──────────────────────────────────────────────────
INSTALLED_APPS = [
    'corsheaders',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

        # Paquetes de terceros
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',

        # Apps del proyecto
    'folium_api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'folium.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# En desarrollo (DEBUG=True) se aceptan todos los orígenes para facilitar el trabajo local.
# En producción (DEBUG=False) solo se permiten los orígenes configurados en FRONTEND_URLS / FRONTEND_URL.
CORS_ALLOW_ALL_ORIGINS = DEBUG

_raw_frontend_urls = os.environ.get('FRONTEND_URLS') or os.environ.get(
    'FRONTEND_URL',
    'http://localhost:5173,http://localhost:3000',
)
FRONTEND_URLS = [
    origin.strip().rstrip('/')
    for origin in _raw_frontend_urls.split(',')
    if origin.strip()
]
FRONTEND_URL = (
    os.environ.get('FRONTEND_URL')
    or (FRONTEND_URLS[0] if FRONTEND_URLS else 'http://localhost:5173')
).strip().rstrip('/')

CORS_ALLOWED_ORIGINS = FRONTEND_URLS

CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip('/')
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', ','.join(FRONTEND_URLS)).split(',')
    if origin.strip()
]

# Permite que el navegador envíe cookies y el header Authorization (necesario para JWT).
CORS_ALLOW_CREDENTIALS = True

# Métodos HTTP que el frontend puede usar.
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Headers que el frontend puede incluir en sus requests.
CORS_ALLOW_HEADERS = [
    'accept',
    'authorization',
    'content-type',
    'origin',
    'x-csrftoken',
    'x-requested-with',
]

WSGI_APPLICATION = 'folium.wsgi.application'



# ─── Base de datos ────────────────────────────────────────────────────────────
# Configuración de PostgreSQL; los valores vienen del archivo .env
# El host 'db' es el nombre del servicio definido en docker-compose.yml
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB'),
        'USER': os.environ.get('POSTGRES_USER'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD'),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}


# ─── Validación de contraseñas ────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# ─── Internacionalización ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-ar'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ─── Archivos estáticos ───────────────────────────────────────────────────────
STATIC_URL = 'static/'

# ─── Archivos de media (subidos por usuarios / seeds) ──────────────────────────
# MEDIA_ROOT es la carpeta real en disco donde se guardan los archivos (ej. portadas).
# Como el volumen del docker-compose monta ".:/app", esta carpeta persiste en el host
# aunque se recree el contenedor. Ya está en .dockerignore, así que no se versiona.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

def get_default_authentication_classes(debug: bool):
    classes = [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ]
    if debug:
        classes.append('rest_framework.authentication.BasicAuthentication')
    return classes


_DEFAULT_AUTH_CLASSES = get_default_authentication_classes(DEBUG)

# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    # Por defecto, solo usuarios autenticados pueden acceder a la API
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'EXCEPTION_HANDLER': 'folium_api.exceptions.custom_exception_handler',
    # Autenticación por JWT y sesión; Basic solo habilitada en desarrollo (DEBUG=True)
    'DEFAULT_AUTHENTICATION_CLASSES': _DEFAULT_AUTH_CLASSES,
    # Throttling / Rate Limiting defensivo contra fuerza bruta y DoS
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/minute',
        'user': '600/minute',
        'auth_login': '30/minute',
    },
}

# ─── JWT (djangorestframework-simplejwt) ──────────────────────────────────────
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# ─── Cabeceras de Seguridad HTTP y Proxy en Producción ───────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
NUM_PROXIES = int(os.environ.get('NUM_PROXIES', '1'))

# Solo activar redirección/cookies Secure cuando exista proxy HTTPS delante de Django
ENABLE_HTTPS_REDIRECT = os.environ.get('ENABLE_HTTPS_REDIRECT', 'False') == 'True'
if not DEBUG and ENABLE_HTTPS_REDIRECT:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'False') == 'True'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ─── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.smtp.EmailBackend'
    if os.environ.get('EMAIL_HOST')
    else 'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@folium.org')