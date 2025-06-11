from django.db import models
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone

class AdminUser(models.Model):
    ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('admin', 'Admin'),
        ('moderator', 'Moderator'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_profile'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='admin')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_admins'
    )
    last_login = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    def has_permission(self, permission):
        """Check if admin user has a specific permission"""
        # Super admins have all permissions
        if self.role == 'super_admin':
            return True

        # Admin users have most permissions except super admin specific ones
        if self.role == 'admin':
            # Define admin-restricted permissions here if needed
            restricted_permissions = ['manage_admins', 'system_settings']
            return permission not in restricted_permissions

        # Moderators have limited permissions
        if self.role == 'moderator':
            allowed_permissions = ['view_users', 'view_content', 'moderate_content']
            return permission in allowed_permissions

        return False

    class Meta:
        verbose_name = "Admin User"
        verbose_name_plural = "Admin Users"

class AdminActivityLog(models.Model):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create_user', 'Create User'),
        ('update_user', 'Update User'),
        ('delete_user', 'Delete User'),
        ('view_dashboard', 'View Dashboard'),
        ('export_data', 'Export Data'),
        ('other', 'Other'),
    ]

    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_activities'
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.admin_user.username} - {self.action} - {self.timestamp}"

    class Meta:
        verbose_name = "Admin Activity Log"
        verbose_name_plural = "Admin Activity Logs"
        ordering = ['-timestamp']

class AdminSession(models.Model):
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='admin_sessions'
    )
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.admin_user.username} - {self.session_key[:8]}..."

    class Meta:
        verbose_name = "Admin Session"
        verbose_name_plural = "Admin Sessions"