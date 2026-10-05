# Guía Paso a Paso: Carga y Gestión de Seeds (Datos de Prueba)

Este documento detalla los pasos para inicializar, aplicar migraciones y cargar los datos de prueba (**seeds**) en el proyecto Folium usando Docker.

---

## 1. Requisitos Previos

Asegurate de contar con el archivo de variables de entorno configurado en la raíz del proyecto. Si no existe, crealo a partir del ejemplo:

```bash
cp .env.example .env
```

Verificá que `.env` contenga `DEBUG=True` para que los seeds automáticos se ejecuten correctamente durante las migraciones.

---

## 2. Iniciar los Contenedores de Docker

Levantá la base de datos PostgreSQL y la aplicación web Django en segundo plano:

```bash
docker compose up -d
```

Podés verificar el estado de los contenedores con:

```bash
docker compose ps
```

---

## 3. Aplicar Migraciones y Carga Automática

El proyecto cuenta con una señal en `folium_api/apps.py` que ejecuta automáticamente el comando de seeding una vez finalizadas las migraciones:

```bash
docker compose exec web python manage.py migrate
```

Al terminar, la terminal mostrará el resumen de registros creados (géneros, autores, libros, copias/ítems, usuarios, préstamos, reservas y reseñas) junto con las credenciales de acceso.

---

## 4. Ejecución y Reinicio Manual del Seeding

Si en cualquier momento necesitás volver a cargar los datos o reiniciar la base sin perder la estructura de tablas, disponés del comando `seed_data`:

### Carga idempotente (no duplica si ya existen):
```bash
docker compose exec web python manage.py seed_data
```

### Reinicio total (borra datos existentes y vuelve a sembrar):
```bash
docker compose exec web python manage.py seed_data --flush
```

---

## 5. Credenciales de Prueba Disponibles

El comando genera automáticamente cuentas con distintos roles para pruebas en el admin y la API:

| Rol | Usuario | Contraseña | Acceso |
| :--- | :--- | :--- | :--- |
| **Administrador** | `admin` | `admin1234` | Panel Django (`/admin/`) y API |
| **Bibliotecario** | `mfernandez` | `biblio1234` | Gestión de préstamos y catálogo |
| **Bibliotecario** | `jperalta` | `biblio1234` | Gestión de préstamos y catálogo |
| **Lector** | `mgomez` | `lector1234` | Catálogo, reservas y reseñas |
| **Lector** | `lrodriguez` | `lector1234` | Catálogo, reservas y reseñas |

*(Existen 4 lectores adicionales: `lector3`, `lector4`, `lector5`, `lector6` con la contraseña `lector1234`).*

---

## 6. Verificación de la API

Podés obtener un token JWT enviando una solicitud `POST` a `/api/v1/token/`:

```bash
curl -X POST http://localhost:8000/api/v1/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin1234"}'
```

Con el token de acceso obtenido (`access`), agregá el encabezado de autorización en tus solicitudes en EchoAPI o Postman:

```text
Authorization: Bearer <tu_token_access>
```

Y consultá los recursos principales:
* Libros: `GET http://localhost:8000/api/v1/book/`
* Copias físicas (ítems): `GET http://localhost:8000/api/v1/items/`
* Préstamos: `GET http://localhost:8000/api/v1/loan/`
