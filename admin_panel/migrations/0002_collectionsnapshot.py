# Generated by Django 4.2.11 on 2024-09-09 20:18

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('admin_panel', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CollectionSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ciq', models.IntegerField(default=0)),
                ('new', models.IntegerField(default=0)),
                ('amount_held', models.FloatField(default=0.0)),
                ('paid', models.FloatField(default=0.0)),
                ('partly_paid', models.FloatField(default=0.0)),
                ('amount_paid', models.FloatField(default=0, max_length=10)),
                ('paid_rate', models.FloatField(default=0.0)),
                ('amount_paid_rate', models.FloatField(default=0.0)),
                ('notes', models.IntegerField(default=0)),
                ('stage', models.CharField(default='', max_length=10)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
