# Generated by Django 5.2 on 2025-04-24 07:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_aiconversation'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='expert_review_completed',
            field=models.BooleanField(default=False),
        ),
    ]
