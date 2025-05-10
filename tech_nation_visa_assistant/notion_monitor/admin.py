from django.contrib import admin
from .models import PageVersion, Change, Notification, NotificationPreference, MonitoredPage, NotionScrapeLog

@admin.register(PageVersion)
class PageVersionAdmin(admin.ModelAdmin):
    list_display = ('title', 'url', 'created_at')
    search_fields = ('title', 'url')
    readonly_fields = ('content_hash',)

@admin.register(Change)
class ChangeAdmin(admin.ModelAdmin):
    list_display = ('section', 'change_type', 'detected_at')
    list_filter = ('change_type', 'detected_at')
    search_fields = ('section', 'description')
    readonly_fields = ('previous_version', 'current_version', 'diff_text', 'diff_html')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'change', 'read', 'created_at')
    list_filter = ('read', 'created_at')
    search_fields = ('user__username', 'change__section')

@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'email_notifications', 'in_app_notifications', 'notify_major_changes_only')
    list_filter = ('email_notifications', 'in_app_notifications', 'notify_major_changes_only')
    search_fields = ('user__username',)

@admin.register(MonitoredPage)
class MonitoredPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'url', 'last_checked')
    search_fields = ('title', 'url')

@admin.register(NotionScrapeLog)
class NotionScrapeLogAdmin(admin.ModelAdmin):
    list_display = ('started_at', 'completed_at', 'status', 'pages_checked', 'changes_detected')
    list_filter = ('status', 'started_at')
    readonly_fields = ('started_at', 'completed_at', 'pages_checked', 'changes_detected', 'error_message')