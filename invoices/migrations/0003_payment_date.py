# Generated by Django 3.1.1 on 2020-09-15 00:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0002_payment'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
