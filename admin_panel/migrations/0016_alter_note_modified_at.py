# Generated by Django 4.2.11 on 2024-05-13 06:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0015_note'),
    ]

    operations = [
        migrations.AlterField(
            model_name='note',
            name='modified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
