# Generated by Django 4.2.11 on 2024-05-31 09:06

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0024_rename_amount_held_collection_amount_due_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='collection',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
