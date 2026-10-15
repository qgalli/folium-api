from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def create_tiers_and_assign_existing_users(apps, schema_editor):
    Tier = apps.get_model("folium_api", "Tier")
    User = apps.get_model("folium_api", "User")
    database = schema_editor.connection.alias

    free_tier, _ = Tier.objects.using(database).get_or_create(
        name="Free",
        defaults={
            "level_rank": 1,
            "monthly_price": Decimal("0.00"),
            "max_active_items": 1,
            "description": "Nivel gratuito",
        },
    )
    Tier.objects.using(database).get_or_create(
        name="Silver",
        defaults={
            "level_rank": 2,
            "monthly_price": Decimal("0.00"),
            "max_active_items": 5,
            "description": "Membresía Silver",
        },
    )
    User.objects.using(database).filter(tier__isnull=True).update(tier_id=free_tier.pk)


class Migration(migrations.Migration):

    dependencies = [
        ("folium_api", "0003_user_favorites"),
    ]

    operations = [
        migrations.CreateModel(
            name="Tier",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=50, unique=True)),
                ("level_rank", models.PositiveSmallIntegerField(unique=True)),
                (
                    "monthly_price",
                    models.DecimalField(
                        decimal_places=2,
                        default=0.0,
                        max_digits=10,
                    ),
                ),
                ("max_active_items", models.PositiveSmallIntegerField()),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddField(
            model_name="book",
            name="editorial",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="user",
            name="tier_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="tier",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="folium_api.tier",
            ),
        ),
        migrations.RunPython(
            create_tiers_and_assign_existing_users,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="user",
            name="tier",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="folium_api.tier",
            ),
        ),
    ]