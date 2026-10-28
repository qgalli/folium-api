# Generated manually to add performance database indexes
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('folium_api', '0008_alter_book_isbn'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='book',
            index=models.Index(fields=['deleted_at'], name='book_deleted_at_idx'),
        ),
        migrations.AddIndex(
            model_name='book',
            index=models.Index(fields=['publication_year'], name='book_pub_year_idx'),
        ),
        migrations.AddIndex(
            model_name='book',
            index=models.Index(fields=['title'], name='book_title_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['status'], name='item_status_idx'),
        ),
        migrations.AddIndex(
            model_name='item',
            index=models.Index(fields=['book', 'status'], name='item_book_status_idx'),
        ),
        migrations.AddIndex(
            model_name='loan',
            index=models.Index(fields=['returned_at'], name='loan_returned_at_idx'),
        ),
        migrations.AddIndex(
            model_name='loan',
            index=models.Index(fields=['due_at'], name='loan_due_at_idx'),
        ),
        migrations.AddIndex(
            model_name='loan',
            index=models.Index(fields=['user', 'returned_at'], name='loan_user_ret_idx'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['status'], name='res_status_idx'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['book', 'status'], name='res_book_status_idx'),
        ),
        migrations.AddIndex(
            model_name='reservation',
            index=models.Index(fields=['user', 'status'], name='res_user_status_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['deleted_at'], name='review_deleted_at_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['book', 'deleted_at'], name='review_book_del_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['rating'], name='review_rating_idx'),
        ),
    ]
