# Diagnóstico de Performance y Optimización: Estado Actual y Próximos Pasos

Este documento resume el problema central de rendimiento pendiente en Folium, la interacción entre Frontend y Backend, y la estrategia para abordarlo sin romper la experiencia de usuario.

---

## 1. Lo que ya quedó resuelto ✅

1. **Exclusión lógica de libros eliminados (`deleted_at`):**
   * Resuelto e integrado con la rama `testing`. Los lectores solo ven libros activos (`deleted_at__isnull=True`), mientras administradores y bibliotecarios pueden auditar eliminados mediante parámetros explícitos (`?deleted_only=true` / `?include_deleted=true`).
2. **Optimización de memoria en `RandomBookView`:**
   * Se eliminó la carga masiva de listas de IDs a la memoria RAM de Python (`list(qs.values_list("id", flat=True))`).
   * Ahora se realiza un muestreo directo por offset aleatorio en base de datos (`qs[random_index]`), con consumo constante $O(1)$.
3. **Limpieza de herramientas invasivas:**
   * Se removió `django-silk` y sus middlewares para evitar bloqueos de I/O en la entrega de imágenes multimedia (`/media/`).

---

## 2. El Problema Central Pendiente: N+1 Queries en el Catálogo de Libros ⚠️

### El síntoma
Cada vez que un usuario ingresa al catálogo general (`/catalog` o `GET /api/v1/book/`), el backend ejecuta **más de 200 consultas SQL independientes** hacia PostgreSQL en una sola petición.

### La causa raíz en el código
En `folium_api/serializers.py` (`BookListSerializer`):
* `get_total_items`: ejecuta `obj.items.count()`.
* `get_available_items`: ejecuta `obj.items.filter(status=AVAILABLE).count()` y `obj.reservations.filter(status=PENDING, item__isnull=True).count()`.
* `get_is_available`: vuelve a ejecutar `get_available_items` (repite las queries anteriores).

Para una página estándar de libros, las consultas se multiplican por cada libro mostrado ($N \times 4$ queries extra).

### Por qué impacta críticamente en AWS
En la capa gratuita de AWS (1 vCPU, 1 GB RAM, pool limitado de conexiones en RDS/Postgres):
* **20 personas navegando simultáneamente** generan más de **4.000 consultas SQL concurrentes**.
* El pool de conexiones de base de datos se agota rápidamente, disparando errores `504 Gateway Timeout` y caídas del servidor.

---

## 3. La Interacción Crítica entre Frontend y Backend (Cuello de Botella Integral)

La lentitud no solo ocurre en la base de datos; la experiencia de usuario depende de cómo dialogan React y Django:

1. **Tamaño de página y volumen de datos:**
   * Si el Frontend solicita demasiados libros por página (ej. 50 libros de golpe), obliga a React a renderizar 50 tarjetas y a descargar 50 imágenes simultáneamente por red.
2. **Descarga simultánea de portadas (`/media/`):**
   * El navegador dispara decenas de peticiones paralelas de imágenes hacia Django (`serve_optimized_media`).
   * Si las imágenes no usan carga diferida (`loading="lazy"`) en el frontend o si no están en formatos livianos (WebP), saturan el ancho de banda y la cola de peticiones.
3. **Contrato de datos entre Front y Back:**
   * El Frontend espera estrictamente:
     - `total_items` (entero).
     - `available_items` (entero).
     - `is_available` (booleano).
   * Cualquier optimización en Django debe devolver exactamente estos mismos tipos y valores para no romper botones de reserva ni etiquetas de stock.
4. **Búsquedas y Filtros:**
   * Verificar que el Frontend implemente `debounce` al escribir en la barra de búsqueda para no disparar una consulta al backend por cada tecla pulsada.

---

## 4. Próximo Paso al pasar a la carpeta del Frontend

Al abrir el proyecto frontend (`folium-web-app`):
1. Inspeccionar cómo consume los libros (`BookCatalog.jsx`, hooks de API).
2. Verificar el tamaño de página configurado (`page_size`).
3. Revisar el componente `BookCard.jsx` (uso de `loading="lazy"`, lectura de `is_available`).
4. Coordinar la optimización del backend para que responda en menos de 50 ms garantizando 100% de compatibilidad visual.
