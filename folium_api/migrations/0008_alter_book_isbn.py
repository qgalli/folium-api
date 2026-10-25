# Generated manually to make Book.isbn optional and nullable
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('folium_api', '0007_editorial_alter_book_editorial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='book',
            name='isbn',
            field=models.CharField(blank=True, max_length=13, null=True, unique=True),
        ),
    ]
