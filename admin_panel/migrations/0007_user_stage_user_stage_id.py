# Generated by Django 4.2.11 on 2024-05-09 08:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0006_remove_user_stage_remove_user_stage_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='stage',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='stage_id',
            field=models.IntegerField(default=1),
        ),
    ]
