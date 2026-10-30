from django.core.management.base import BaseCommand

from folium_api.billing_models import SubscriptionPlan


class Command(BaseCommand):
    help = "Sincroniza la tabla de planes con el catálogo oficial de MercadoPago." 

    def handle(self, *args, **options):
        plans = SubscriptionPlan.sync_from_catalog()
        self.stdout.write(
            self.style.SUCCESS(f"Sincronizados {len(plans)} planes de suscripción.")
        )
