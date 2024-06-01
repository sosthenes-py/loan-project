# Generated by Django 4.2.11 on 2024-05-09 15:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('loan_app', '0002_alter_user_address_alter_user_bvn_alter_user_dob_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='address',
            field=models.CharField(blank=True, default='', max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='bvn',
            field=models.CharField(blank=True, default='', max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='email2',
            field=models.EmailField(blank=True, default='', max_length=254, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='last_name',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='user',
            name='middle_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='phone2',
            field=models.CharField(blank=True, default='', max_length=15, null=True),
        ),
    ]
