# Generated by Django 4.2.11 on 2024-06-01 14:26

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0024_loan_repaid_at'),
        ('admin_panel', '0028_remove_waive_app_user'),
    ]

    operations = [
        migrations.AlterField(
            model_name='waive',
            name='loan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='loan_app.loan'),
        ),
    ]
