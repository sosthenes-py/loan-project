# Generated by Django 4.2.11 on 2024-06-27 17:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0007_contact_created_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='loan',
            name='interest_perc',
            field=models.FloatField(default=40),
        ),
    ]
