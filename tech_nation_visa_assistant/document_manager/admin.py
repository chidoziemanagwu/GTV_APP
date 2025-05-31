from django.contrib import admin
from .models import EligibilityCriteria, Document, DocumentComment, UserPoints, PointsPackage, PointsTransaction

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

class UserPointsAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'lifetime_points', 'last_purchase')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('lifetime_points',)

class PointsPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'points', 'price', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')

class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ['user', 'package', 'points', 'amount', 'payment_status', 'created_at']
    list_filter = ['payment_status']
    search_fields = ['user__username', 'stripe_payment_intent_id', 'stripe_checkout_id']
    readonly_fields = ['created_at', 'updated_at']

admin.site.register(PointsTransaction, PointsTransactionAdmin)
admin.site.register(PointsPackage)
admin.site.register(UserPoints)
admin.site.register(Document)
admin.site.register(DocumentComment)
admin.site.register(EligibilityCriteria)