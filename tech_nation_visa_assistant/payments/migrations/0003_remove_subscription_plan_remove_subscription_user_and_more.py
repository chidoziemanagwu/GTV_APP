# Generated by Django 5.2 on 2025-05-08 22:54

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('expert_marketplace', '0012_remove_expert_user_remove_service_expert_and_more'),
        ('payments', '0002_alter_payment_service'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='subscription',
            name='plan',
        ),
        migrations.RemoveField(
            model_name='subscription',
            name='user',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='subscription',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='currency',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='payment_type',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='service',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='stripe_payment_id',
        ),
        migrations.RemoveField(
            model_name='payment',
            name='user',
        ),
        migrations.AddField(
            model_name='payment',
            name='booking',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='payment', to='expert_marketplace.booking'),
        ),
        migrations.AddField(
            model_name='payment',
            name='stripe_payment_intent_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.DeleteModel(
            name='Booking',
        ),
        migrations.DeleteModel(
            name='SubscriptionPlan',
        ),
        migrations.DeleteModel(
            name='Subscription',
        ),
    ]
