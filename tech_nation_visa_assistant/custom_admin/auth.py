from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps
from .models import AdminUser, AdminActivityLog, AdminSession
import uuid
from django.utils import timezone




def create_admin_session(admin_user, request):
    """Create a new admin session record"""
    AdminSession.objects.create(
        admin_user=admin_user.user,  # Use admin_user.user instead of admin_user
        session_key=request.session.session_key,
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        last_activity=timezone.now()
    )


def admin_required(permission=None):
    """Decorator to check if user is a custom admin with optional permission"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('custom_admin:login')

            try:
                admin_user = AdminUser.objects.get(user=request.user, is_active=True)

                # Check specific permission if provided
                if permission and not admin_user.has_permission(permission):
                    messages.error(request, "You don't have permission to access this page.")
                    return redirect('custom_admin:dashboard')

                # Update last activity
                request.admin_user = admin_user
                admin_user.last_login = timezone.now()
                admin_user.save()

                return view_func(request, *args, **kwargs)

            except AdminUser.DoesNotExist:
                messages.error(request, "You are not authorized to access the admin panel.")
                return redirect('custom_admin:login')

        return _wrapped_view

    # Handle case where decorator is used without arguments
    if callable(permission):
        view_func = permission
        permission = None
        return decorator(view_func)

    return decorator




def log_admin_activity(admin_user, action, description, target_model=None, target_id=None, request=None):
    """Log admin activity"""
    # Ensure action is one of the defined choices or use 'other'
    from .models import AdminActivityLog
    valid_actions = [choice[0] for choice in AdminActivityLog.ACTION_CHOICES]

    if action not in valid_actions:
        action = 'other'

    activity_data = {
        'admin_user': admin_user.user,  # Use admin_user.user instead of admin_user
        'action': action,
        'description': description,
    }

    # If target_model and target_id are provided, include them in the description
    if target_model and target_id:
        activity_data['description'] += f" (Target: {target_model} #{target_id})"

    if request:
        activity_data['ip_address'] = request.META.get('REMOTE_ADDR', '')
        activity_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')

    return AdminActivityLog.objects.create(**activity_data)