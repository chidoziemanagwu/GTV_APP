from django.contrib import admin
from .models import AIQuery, AIFeedback

class AIFeedbackInline(admin.TabularInline):
    model = AIFeedback
    extra = 0

class AIQueryAdmin(admin.ModelAdmin):
    list_display = ('user', 'query_text_short', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'query_text', 'response_text')
    inlines = [AIFeedbackInline]

    def query_text_short(self, obj):
        return obj.query_text[:50] + '...' if len(obj.query_text) > 50 else obj.query_text
    query_text_short.short_description = 'Query'

admin.site.register(AIQuery, AIQueryAdmin)
admin.site.register(AIFeedback)