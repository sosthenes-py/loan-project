# Generated by Django 4.2.11 on 2024-05-18 01:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0020_rename_bank_disbursementaccount_bank_code_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loan',
            name='duration',
            field=models.IntegerField(default=6),
        ),
    ]
