# Generated by Django 3.1.2 on 2022-07-23 10:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('invoices', '0022_invnum_invoicecounter'),
    ]

    operations = [
        migrations.AddField(
            model_name='usersystem',
            name='billing_term',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='invoices.term'),
        ),
    ]