# Generated by Django 4.2.11 on 2024-06-25 17:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0005_smslog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='smslog',
            name='date',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
