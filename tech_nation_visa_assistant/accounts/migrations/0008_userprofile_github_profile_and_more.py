# Generated by Django 5.2 on 2025-04-26 12:11

import django_countries.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_activity'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='github_profile',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='linkedin_profile',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='portfolio_website',
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='current_country',
            field=django_countries.fields.CountryField(blank=True, max_length=2, null=True),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='target_uk_region',
            field=models.CharField(blank=True, choices=[('london', 'London'), ('south_east', 'South East'), ('south_west', 'South West'), ('east_england', 'East of England'), ('west_midlands', 'West Midlands'), ('east_midlands', 'East Midlands'), ('yorkshire', 'Yorkshire and the Humber'), ('north_west', 'North West'), ('north_east', 'North East'), ('wales', 'Wales'), ('scotland', 'Scotland'), ('northern_ireland', 'Northern Ireland')], max_length=50, null=True),
        ),
    ]
