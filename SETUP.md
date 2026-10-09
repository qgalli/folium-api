# __folium__ — Instrucciones de instalación y configuración del entorno

#### Escrito con IA pero todo chequeado por Quimey. Todo funciona.

Ante cualquier duda sobre como configurar alguna de estas cositas busquen en internet o preguntenle a la IA, o preguntenme a mí y veo en que los puedo ayudar.

---

## Antes de empezar — Instalá los programas necesarios

Necesitás dos programas instalados. Si ya los tenés, pasá al siguiente paso.

### 1. Git

Git es el programa que te permite descargar el código del proyecto.

- Windows: Descargalo desde [https://git-scm.com/downloads](https://git-scm.com/downloads) e instalalo con todas las opciones por defecto.
- Linux (Ubuntu/Debian): Abrí una terminal y ejecutá:
  ```
  sudo apt install git
  ```

### 2. Docker Desktop

Docker es el programa que hace correr la aplicación. Incluye todo lo necesario para que funcione.

- Descargalo desde: [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/)
- Instalalo y abrilo antes de continuar. Tiene que estar corriendo (vas a ver un ícono de ballena en la barra de tareas).

---

## Paso 1 — Descargar el proyecto

Abrí una terminal (en Windows se llama "Símbolo del sistema" o "PowerShell") y ejecutá este comando:

```
git clone https://github.com/TU_USUARIO/folium.git
```

> Reemplazá `TU_USUARIO` con el usuario real de GitHub del proyecto.

Después, entrá a la carpeta del proyecto:

```
cd folium
```

---

## Paso 2 — Crear el archivo de configuración

El proyecto necesita un archivo llamado `.env` con algunos datos de configuración (como contraseñas de la base de datos). Este archivo no está en GitHub por seguridad, así que tenés que crearlo vos.

En Linux, ejecutá:
```
cp .env.example .env
```

En Windows (PowerShell), ejecutá:
```
copy .env.example .env
```

Esto crea tu archivo `.env` a partir de la plantilla de ejemplo. Por ahora no necesitás cambiar nada adentro — los valores por defecto funcionan para desarrollo local.

---

## Paso 3 — Levantar la aplicación

Ejecutá este comando. La primera vez puede tardar varios minutos, es normal — está descargando todo lo necesario:

```
docker compose up --build
```

Cuando veas esta línea en la terminal, significa que todo está funcionando:

```
web-1  | Starting WSGI development server at http://0.0.0.0:8000/
```

Dejá esta terminal abierta mientras usás la aplicación. Si la cerrás, la aplicación se apaga.

---

## Paso 4 — Preparar la base de datos

Sin cerrar la terminal anterior, abrí una nueva terminal, entrá de nuevo a la carpeta del proyecto y ejecutá:

```
cd folium
docker compose exec web python manage.py migrate
```

Este comando crea las tablas necesarias en la base de datos. Solo necesitás hacerlo la primera vez, o cuando alguien del equipo avise que hay cambios en la base de datos.

---

## Acceso a la aplicación

Una vez completados los pasos anteriores, la aplicación está disponible desde el navegador en:

- API: http://localhost:8080
- Panel de administración: http://localhost:8080/admin

---

## Cómo apagar la aplicación

Cuando termines de trabajar, volvé a la terminal donde está corriendo Docker y presioná:

```
Ctrl + C
```

---

## Cómo volver a levantar la aplicación (las próximas veces)

La segunda vez en adelante es mucho más rápido. Solo ejecutá:

```
docker compose up
```

El `--build` solo se necesita la primera vez, o cuando alguien cambia las dependencias del proyecto.

---

## Cómo ver los cambios de tus compañeros

Cuando alguien del equipo suba cambios al proyecto, para verlos en tu computadora:

1. Descargá los cambios:
```
git pull
```

2. Si alguien avisó que hubo cambios en la base de datos, ejecutá también:
```
docker compose exec web python manage.py migrate
```

3. Si alguien avisó que se agregaron nuevas dependencias, ejecutá:
```
docker compose up --build
```

Si nadie avisó nada especial, con el `git pull` alcanza y los cambios se aplican solos.

---

## Solución de problemas comunes

### "permission denied" al ejecutar Docker (solo Linux)

Ejecutá estos dos comandos y volvé a intentar:
```
sudo usermod -aG docker $USER
newgrp docker
```

### "port is already in use" (el puerto ya está en uso)

Otro programa está usando el puerto 8080 o 5432. Reiniciá tu computadora e intentá de nuevo.

### Docker no arranca o da error de conexión

Asegurate de que Docker Desktop esté abierto y corriendo (ícono de ballena en la barra de tareas).

### Cualquier otro error

Copiá el mensaje de error completo y compartilo con el equipo de desarrollo.

