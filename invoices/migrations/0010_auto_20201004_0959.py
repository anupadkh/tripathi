# Generated by Django 3.1.2 on 2020-10-04 04:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0009_auto_20201003_0651'),
    ]

    operations = [
        migrations.AlterField(
            model_name='openingbalance',
            name='amount',
            field=models.FloatField(verbose_name='Opening Balance'),
        ),
    ]
