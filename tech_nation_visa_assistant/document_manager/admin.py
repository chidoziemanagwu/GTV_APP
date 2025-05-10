from django.contrib import admin
from .models import EligibilityCriteria, Document, DocumentComment

class DocumentCommentInline(admin.TabularInline):
    model = DocumentComment
    extra = 0

class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'document_type', 'status', 'created_at', 'updated_at')
    list_filter = ('document_type', 'status', 'created_at')
    search_fields = ('title', 'user__email', 'content')
    inlines = [DocumentCommentInline]

class EligibilityCriteriaAdmin(admin.ModelAdmin):
    list_display = ('name', 'criteria_type', 'applicable_path', 'number_of_documents')
    list_filter = ('criteria_type', 'applicable_path')
    search_fields = ('name', 'description')

admin.site.register(EligibilityCriteria, EligibilityCriteriaAdmin)
admin.site.register(Document, DocumentAdmin)
admin.site.register(DocumentComment)