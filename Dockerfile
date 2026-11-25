# Imagen base oficial de Python 3.12 en su versión slim 
FROM python:3.12-slim

# Evita que Python genere archivos .pyc en disco
ENV PYTHONDONTWRITEBYTECODE=1
# Asegura que la salida de Python se envíe directo al terminal (útil para los logs)
ENV PYTHONUNBUFFERED=1

# Define el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalamos las dependencias primero (capa separada = rebuilds más rápidos si solo cambia el código)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto de los archivos del proyecto
COPY . .

# Exponemos el puerto en el que corre Django
EXPOSE 8000

# Iniciamos el servidor WSGI de producción con Gunicorn
CMD ["gunicorn", "folium.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]

