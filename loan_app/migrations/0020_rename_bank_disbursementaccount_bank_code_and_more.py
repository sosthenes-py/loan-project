# Generated by Django 4.2.11 on 2024-05-16 18:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0019_loan_loan_id'),
    ]

    operations = [
        migrations.RenameField(
            model_name='disbursementaccount',
            old_name='bank',
            new_name='bank_code',
        ),
        migrations.AddField(
            model_name='disbursementaccount',
            name='bank_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.CreateModel(
            name='VirtualAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.CharField(blank=True, max_length=100, null=True)),
                ('bank_name', models.CharField(blank=True, max_length=100, null=True)),
                ('bank_code', models.CharField(blank=True, max_length=100, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to='loan_app.appuser')),
            ],
        ),
    ]
