# Generated by Django 4.2.11 on 2024-07-20 23:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0020_alter_loan_duration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appuser',
            name='eligible_amount',
            field=models.FloatField(default=10000),
        ),
    ]
