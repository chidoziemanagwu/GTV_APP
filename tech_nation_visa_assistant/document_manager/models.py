from django.db import models
from accounts.models import User

class EligibilityCriteria(models.Model):
    TYPE_CHOICES = (
        ('mandatory', 'Mandatory'),
        ('optional', 'Optional'),
    )
    PATH_CHOICES = (
        ('talent', 'Exceptional Talent'),
        ('promise', 'Exceptional Promise'),
        ('both', 'Both Paths'),
    )

    name = models.CharField(max_length=200)
    description = models.TextField()
    criteria_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    applicable_path = models.CharField(max_length=10, choices=PATH_CHOICES)
    number_of_documents = models.IntegerField(default=2)
    notion_link = models.URLField(blank=True)

    def __str__(self):
        return f"{self.criteria_type.title()} - {self.name}"

# document_manager/models.py

class Document(models.Model):
    STATUS_CHOICES = (
        ('not_started', 'Not Started'),
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('reviewing', 'Under Review'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    )

    TYPE_CHOICES = (
        ('personal_statement', 'Personal Statement'),
        ('cv', 'CV'),
        ('recommendation', 'Recommendation Letter'),
        ('evidence', 'Evidence Document'),
        ('other', 'Other'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    related_criteria = models.ForeignKey(
        EligibilityCriteria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Content and File
    content = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='user_documents/', null=True, blank=True)

    # Status and Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    is_generated = models.BooleanField(default=False)
    generation_prompt = models.TextField(blank=True, null=True)

    # Document Analysis
    word_count = models.IntegerField(default=0)
    page_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    source_cv = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_documents',
        help_text="If this is a personal statement, links to the CV used to generate it"
    )

    original_file = models.FileField(
        upload_to='original_documents/',
        null=True,
        blank=True,
        help_text="Original uploaded document"
    )

    generated_file = models.FileField(
        upload_to='generated_documents/',
        null=True,
        blank=True,
        help_text="Generated document in DOCX format"
    )

    is_chosen = models.BooleanField(
        default=False,
        help_text="Indicates if this document is the user's chosen version for submission"
    )
    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} - {self.get_document_type_display()}"

    @property
    def has_original_file(self):
        return bool(self.original_file)

    def generate_docx(self):
        """Generate a DOCX file with disclaimer"""
        from docx import Document as DocxDocument

        doc = DocxDocument()

        # Add disclaimer
        disclaimer = doc.add_paragraph()
        disclaimer.add_run("DISCLAIMER").bold = True
        doc.add_paragraph(
            "This document is auto-generated for sample purposes only. "
            "It should be thoroughly reviewed, customized, and edited to reflect "
            "your personal experiences and achievements. Do not submit this "
            "document as-is for your visa application."
        )

        # Add a divider
        doc.add_paragraph("=" * 50)

        # Add the main content
        doc.add_paragraph(self.content)

        # Save the file
        filename = f"{self.title}_{self.id}.docx"
        filepath = f"generated_documents/{filename}"
        doc.save(filepath)

        # Update the generated_file field
        self.generated_file.name = filepath
        self.save()

    def get_file_extension(self):
        if self.file:
            return self.file.name.split('.')[-1].lower()
        return None



class DocumentComment(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment on {self.document.title}"