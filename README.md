# Folium API — Guía de desarrollo con Docker

## Requisitos previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado y corriendo
- Git

---

## Primeros pasos

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd folium
```

### 2. Crear el archivo de variables de entorno

Copiá el archivo de ejemplo y completá los valores:

```bash
cp .env.example .env
```

Editá `.env` con tus credenciales. El archivo `.env` **nunca debe commitearse** al repositorio.

---

## Levantar el proyecto

```bash
docker compose up --build
```

Esto construye la imagen de Django e inicia dos contenedores:
- **`web`** → Django corriendo en [http://localhost:8000](http://localhost:8000)
- **`db`** → PostgreSQL en el puerto `5432`

La primera vez puede tardar un poco mientras Docker descarga las imágenes base.

---

## Comandos útiles

### Correr las migraciones (primera vez y cada vez que haya cambios en modelos)

```bash
docker compose exec web python manage.py migrate
```

### Crear un superusuario para el panel de administración

```bash
docker compose exec web python manage.py createsuperuser
```

Luego accedé al admin en [http://localhost:8000/admin](http://localhost:8000/admin).

### Crear nuevas migraciones después de modificar modelos

```bash
docker compose exec web python manage.py makemigrations
```

### Ver los logs en tiempo real

```bash
docker compose logs -f
```

### Detener los contenedores

```bash
docker compose down
```

### Detener y eliminar los datos de la base de datos (¡cuidado!)

```bash
docker compose down -v
```

---

## Estructura del proyecto

```
folium/
├── .dockerignore        # Archivos excluidos del build de Docker
├── .env                 # Variables de entorno locales (NO commitear)
├── .env.example         # Plantilla de variables de entorno (sí commitear)
├── .gitignore
├── Dockerfile           # Imagen de la app Django
├── docker-compose.yml   # Orquestación de contenedores (Django + PostgreSQL)
├── manage.py
├── requirements.txt     # Dependencias de Python
├── folium/              # Configuración principal de Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── folium_api/          # App principal de la API
    ├── models.py
    ├── views.py
    └── ...
```

---

## Variables de entorno

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave secreta de Django. Generá una nueva con el comando de abajo. |
| `DEBUG` | `True` en desarrollo, `False` en producción. |
| `POSTGRES_DB` | Nombre de la base de datos. |
| `POSTGRES_USER` | Usuario de PostgreSQL. |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL. |

**Para generar una nueva `SECRET_KEY`:**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Notas importantes

> [!WARNING]
> Nunca commitees el archivo `.env` al repositorio. Contiene credenciales sensibles.

> [!NOTE]
> El hot reload está activado: cualquier cambio en el código Python se refleja automáticamente sin necesidad de reiniciar el contenedor.

> [!TIP]
> Para conectarte a la base de datos con un cliente como **DBeaver** o **TablePlus**, usá `localhost:5432` con las credenciales de tu `.env`.

