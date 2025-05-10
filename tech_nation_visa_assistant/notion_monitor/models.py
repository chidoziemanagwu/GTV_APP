from django.db import models
from django.conf import settings

class MonitoredPage(models.Model):
    """A Notion page that is being monitored for changes"""
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=255)
    last_checked = models.DateTimeField(auto_now=True)
    content_hash = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self):
        return self.title

class PageVersion(models.Model):
    """A version of a Notion page"""
    url = models.URLField(max_length=500)
    title = models.CharField(max_length=255)
    content_text = models.TextField()
    content_html = models.TextField()
    content_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class Change(models.Model):
    """A detected change in a Notion page"""
    CHANGE_TYPES = (
        ('major', 'Major Change'),
        ('minor', 'Minor Change'),
    )

    section = models.CharField(max_length=255)
    url = models.URLField(max_length=500)
    previous_version = models.ForeignKey(PageVersion, on_delete=models.CASCADE, related_name='previous_changes')
    current_version = models.ForeignKey(PageVersion, on_delete=models.CASCADE, related_name='current_changes')
    description = models.TextField()
    diff_text = models.TextField()
    diff_html = models.TextField()
    change_type = models.CharField(max_length=10, choices=CHANGE_TYPES, default='minor')
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detected_at']

    def __str__(self):
        return f"Change in {self.section} - {self.detected_at.strftime('%Y-%m-%d %H:%M')}"

class Notification(models.Model):
    """A notification for a user about a change"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notion_notifications')
    change = models.ForeignKey(Change, on_delete=models.CASCADE, related_name='notifications')
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

class NotificationPreference(models.Model):
    """User preferences for notifications"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notion_notification_preference')
    email_notifications = models.BooleanField(default=True)
    in_app_notifications = models.BooleanField(default=True)
    notify_major_changes_only = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification preferences for {self.user.username}"

class NotionScrapeLog(models.Model):
    """Log of scraping activities"""
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    pages_checked = models.IntegerField(default=0)
    changes_detected = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=[
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ], default='in_progress')
    error_message = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Scrape log from {self.started_at}"