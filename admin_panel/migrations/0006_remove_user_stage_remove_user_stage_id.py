# Generated by Django 4.2.11 on 2024-05-09 08:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0005_alter_user_stage_alter_user_stage_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='stage',
        ),
        migrations.RemoveField(
            model_name='user',
            name='stage_id',
        ),
    ]
