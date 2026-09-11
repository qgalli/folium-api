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

# Hosts permitidos; en desarrollo con Docker se acepta cualquier host
ALLOWED_HOSTS = ['*']

# Le dice a Django que use nuestro modelo de usuario personalizado en lugar del que viene por defecto
AUTH_USER_MODEL = 'folium_api.User'

# ─── Aplicaciones instaladas ──────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

        # Paquetes de terceros
    'rest_framework',

        # Apps del proyecto
    'folium_api',
]

MIDDLEWARE = [
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
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ─── Archivos estáticos ───────────────────────────────────────────────────────
STATIC_URL = 'static/'


# ─── Django REST Framework ────────────────────────────────────────────────────
REST_FRAMEWORK = {
    # Por defecto, solo usuarios autenticados pueden acceder a la API
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Autenticación por sesión (navegador) y autenticación básica (para desarrollo)
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],
}


# ─── Email ────────────────────────────────────────────────────────────────────
MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
