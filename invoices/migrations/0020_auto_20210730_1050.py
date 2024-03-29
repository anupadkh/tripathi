# Generated by Django 3.1.2 on 2021-07-30 05:05

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0019_usersystem_default_term'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='term',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='invoices.term'),
        ),
        migrations.AlterField(
            model_name='payment',
            name='payment_mode',
            field=models.IntegerField(choices=[(1, 'Cheque'), (2, 'Cash'), (3, 'Bank Transfer'), (4, 'Internet Payment'), (5, 'Transport'), (6, 'Bank Deposit'), (7, 'Goods Returned'), (8, 'Discount')]),
        ),
    ]
