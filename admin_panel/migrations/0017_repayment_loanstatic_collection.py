# Generated by Django 4.2.11 on 2024-05-15 19:51

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0015_loan'),
        ('admin_panel', '0016_alter_note_modified_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='Repayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_held', models.FloatField(default=0, max_length=10)),
                ('amount_paid', models.FloatField(default=0, max_length=10)),
                ('total_paid', models.FloatField(default=0, max_length=10)),
                ('stage', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('admin_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('loan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='loan_app.loan')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='loan_app.appuser')),
            ],
        ),
        migrations.CreateModel(
            name='LoanStatic',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(blank=True, max_length=100, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('loan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='loan_app.loan')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Collection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount_held', models.FloatField(max_length=15)),
                ('amount_paid', models.FloatField(default=0, max_length=10)),
                ('stage', models.IntegerField(max_length=0)),
                ('loan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='loan_app.loan')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
