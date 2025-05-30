# Generated by Django 5.2 on 2025-04-21 21:35

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='pending', max_length=10)),
                ('scheduled_time', models.DateTimeField()),
                ('notes', models.TextField(blank=True)),
                ('payment_completed', models.BooleanField(default=False)),
                ('payment_amount', models.DecimalField(decimal_places=2, max_digits=6)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Expert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specialization', models.CharField(choices=[('technical', 'Technical'), ('business', 'Business'), ('both', 'Both Technical & Business')], max_length=20)),
                ('bio', models.TextField()),
                ('hourly_rate', models.DecimalField(decimal_places=2, max_digits=6)),
                ('years_experience', models.IntegerField()),
                ('success_rate', models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ('is_verified', models.BooleanField(default=False)),
                ('verification_documents', models.FileField(blank=True, null=True, upload_to='expert_verification/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='expert_profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.IntegerField(choices=[(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)])),
                ('comment', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('booking', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='review', to='expert_marketplace.booking')),
            ],
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField()),
                ('tier', models.CharField(choices=[('basic', 'Basic Review'), ('standard', 'Standard Review'), ('premium', 'Premium Review')], max_length=10)),
                ('price', models.DecimalField(decimal_places=2, max_digits=6)),
                ('duration_minutes', models.IntegerField()),
                ('expert', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='services', to='expert_marketplace.expert')),
            ],
        ),
        migrations.AddField(
            model_name='booking',
            name='service',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bookings', to='expert_marketplace.service'),
        ),
    ]
