# Generated by Django 4.0.7 on 2024-06-29 15:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0003_alter_baseuser_signature'),
    ]

    operations = [
        migrations.AlterField(
            model_name='baseuser',
            name='signature',
            field=models.ImageField(blank=True, null=True, upload_to='images'),
        ),
    ]