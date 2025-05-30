# Generated by Django 5.2 on 2025-04-26 12:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('document_manager', '0003_alter_document_options_document_generation_prompt_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='generated_file',
            field=models.FileField(blank=True, help_text='Generated document in DOCX format', null=True, upload_to='generated_documents/'),
        ),
        migrations.AddField(
            model_name='document',
            name='original_file',
            field=models.FileField(blank=True, help_text='Original uploaded document', null=True, upload_to='original_documents/'),
        ),
        migrations.AddField(
            model_name='document',
            name='source_cv',
            field=models.ForeignKey(blank=True, help_text='If this is a personal statement, links to the CV used to generate it', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_documents', to='document_manager.document'),
        ),
    ]
