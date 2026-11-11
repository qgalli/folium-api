import os
import sys

from django.apps import AppConfig
from django.db.models.signals import post_migrate


class FoliumApiConfig(AppConfig):
    name = 'folium_api'

    def ready(self):
        # Conecta la señal post_migrate para que, cada vez que se corra
        # `python manage.py migrate`, se carguen automáticamente los datos
        # de prueba (seeds). El comando `seed_data` es idempotente
        # (usa get_or_create), así que correrlo varias veces no duplica nada.
        post_migrate.connect(self._run_seed_data, sender=self)

    def _run_seed_data(self, **kwargs):
        # No cargar seeds durante los tests automatizados para no
        # contaminar la base de datos de prueba con datos preexistentes.
        if 'test' in sys.argv:
            return

        # Solo se ejecuta en desarrollo (DEBUG=True), nunca en producción,
        # para evitar cargar datos de prueba en una base de datos real.
        if os.environ.get('DEBUG', 'False') != 'True':
            return

        from django.core.management import call_command

        call_command('seed_data')
