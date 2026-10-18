from django.db import migrations, models


def populate_dni_for_existing_users(apps, schema_editor):
    User = apps.get_model("folium_api", "User")
    database = schema_editor.connection.alias

    users_without_dni = User.objects.using(database).filter(dni__isnull=True).order_by("id")
    for user in users_without_dni:
        user.dni = 10000000 + user.id
        user.save(update_fields=["dni"])


class Migration(migrations.Migration):

    dependencies = [
        ("folium_api", "0004_tiers_membership_editorial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="dni",
            field=models.IntegerField(null=True),
        ),
        migrations.RunPython(
            populate_dni_for_existing_users,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="user",
            name="dni",
            field=models.IntegerField(unique=True),
        ),
    ]
