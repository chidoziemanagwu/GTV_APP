# Generated by Django 5.2 on 2025-04-24 07:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_userprofile_expert_review_completed'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='application_submitted',
            field=models.BooleanField(default=False),
        ),
    ]
