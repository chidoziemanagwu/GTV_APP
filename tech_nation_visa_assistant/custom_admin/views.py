from django.shortcuts import render
import traceback
# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import timedelta
import json
from django.views.decorators.http import require_POST

from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import AdminUser, AdminActivityLog
from .auth import admin_required, log_admin_activity, create_admin_session
from document_manager.models import UserPoints, PointsTransaction
from accounts.models import Activity, ContactMessage
from .models import AdminUser
from .models import AdminSession
from accounts.models import User, ContactMessage
from django.core.mail import send_mail
from django.conf import settings
from .auth import admin_required

from datetime import datetime, timedelta
from django.db.models import Sum, Q, Count, Avg, F, ExpressionWrapper, FloatField, Case, When, Value, CharField, DecimalField
from django.db.models.functions import Coalesce
from expert_marketplace.models import Booking, Expert, NoShowDispute, Consultation, ExpertEarning, ExpertBonus
import csv
from django.http import HttpResponse
from referrals.models import ReferralClick, ReferralCode, ReferralSignup
from django.http import JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

import logging
import stripe
from payments.models import Payment
from expert_marketplace.stripe_service import process_refund as process_stripe_refund # ADD THIS LINE
# Configure logging
from expert_marketplace.models import Expert # Ensure Expert is imported
from django.urls import reverse
from django.core.exceptions import ValidationError # Add this import if not already there
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation # Make sure ROUND_HALF_UP is here


logger = logging.getLogger(__name__)
User = get_user_model()

def validate_availability_json_list_format(json_string):
    """
    Validates that the provided JSON string is a list of availability slots
    with 'date', 'start_time', and 'end_time'.
    Returns the validated JSON string if valid, otherwise raises ValidationError.
    """
    if not json_string:
        return "[]" # Empty string is valid, represents no slots

    try:
        data = json.loads(json_string)
    except json.JSONDecodeError:
        raise ValidationError("Invalid JSON format.")

    if not isinstance(data, list):
        raise ValidationError("Availability data must be a JSON list (array).")

    for i, slot in enumerate(data):
        if not isinstance(slot, dict):
            raise ValidationError(f"Slot at index {i} is not a valid object.")
        
        required_keys = {"date", "start_time", "end_time"}
        if not required_keys.issubset(slot.keys()):
            missing_keys = required_keys - slot.keys()
            raise ValidationError(f"Slot at index {i} is missing keys: {', '.join(missing_keys)}.")

        try:
            datetime.strptime(slot['date'], '%Y-%m-%d')
        except ValueError:
            raise ValidationError(f"Slot at index {i} has invalid date format for '{slot['date']}'. Use YYYY-MM-DD.")
        
        try:
            datetime.strptime(slot['start_time'], '%H:%M')
        except ValueError:
            raise ValidationError(f"Slot at index {i} has invalid start_time format for '{slot['start_time']}'. Use HH:MM.")
        
        try:
            datetime.strptime(slot['end_time'], '%H:%M')
        except ValueError:
            raise ValidationError(f"Slot at index {i} has invalid end_time format for '{slot['end_time']}'. Use HH:MM.")
        
        if slot['start_time'] >= slot['end_time']:
            raise ValidationError(f"Slot at index {i}: start_time ({slot['start_time']}) must be before end_time ({slot['end_time']}).")

    return json.dumps(data) # Return the potentially reformatted (but validated) JSON string

def _recalculate_and_update_single_expert_rating(expert_id):
    """
    Recalculates and updates the average rating for a single expert.
    Saves the new rating to the Expert model.
    Returns True if successful or no change needed, False on error.
    """
    try:
        expert_to_update = Expert.objects.get(id=expert_id)
        
        new_average_rating_data = Consultation.objects.filter(
            expert=expert_to_update,
            status='completed', 
            client_rating_for_expert__isnull=False 
        ).aggregate(avg_rating=Avg('client_rating_for_expert'))
        
        avg_rating_val = new_average_rating_data['avg_rating']
        
        calculated_expert_rating = Decimal(str(avg_rating_val)) if avg_rating_val is not None else Decimal('0.00')
        calculated_expert_rating = calculated_expert_rating.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if expert_to_update.rating != calculated_expert_rating:
            old_rating = expert_to_update.rating
            expert_to_update.rating = calculated_expert_rating
            expert_to_update.save(update_fields=['rating'])
            logger.info(f"RATING_RECALC: Updated rating for expert {expert_to_update.full_name} (ID: {expert_id}) from {old_rating} to {calculated_expert_rating:.2f}")
        return True
            
    except Expert.DoesNotExist:
        logger.error(f"RATING_RECALC: Expert with ID {expert_id} not found for rating update.")
        return False
    except Exception as e:
        logger.error(f"RATING_RECALC: Error updating rating for expert {expert_id}: {str(e)}", exc_info=True)
        return False




def build_absolute_uri(request, view_name, *args, **kwargs):
    """Helper to build absolute URIs, falling back if request is None."""
    if request:
        return request.build_absolute_uri(reverse(view_name, args=args, kwargs=kwargs))
    # Fallback for contexts where request might not be available (e.g., management commands)
    # This requires SITE_DOMAIN to be set in settings.
    site_domain = getattr(settings, 'SITE_DOMAIN', 'http://localhost:8000')
    return f"{site_domain}{reverse(view_name, args=args, kwargs=kwargs)}"



def admin_login(request):
    """Custom admin login"""
    if request.method == 'POST':
        username = request.POST.get('username')  # Changed from 'email'
        password = request.POST.get('password')

        # Try to authenticate with username
        user = authenticate(request, username=username, password=password)

        # If that fails and username looks like an email, try to find the user by email
        if not user and '@' in username:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user_obj = User.objects.get(email=username)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user:
            try:
                admin_user = AdminUser.objects.get(user=user, is_active=True)
                login(request, user)
                create_admin_session(admin_user, request)

                log_admin_activity(
                    admin_user,
                    'login',
                    'Admin logged in successfully',
                    request=request
                )

                messages.success(request, 'Welcome to the admin panel!')
                return redirect('custom_admin:dashboard')

            except AdminUser.DoesNotExist:
                messages.error(request, 'You are not authorized to access the admin panel.')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'custom_admin/login.html')




def admin_logout(request):
    """Custom admin logout"""
    if hasattr(request, 'admin_user'):
        log_admin_activity(
            request.admin_user,
            'logout',
            'Admin logged out',
            request=request
        )

    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('custom_admin:login')


@admin_required
@require_POST
def bulk_user_action(request):
    try:
        data = json.loads(request.body)
        action_type = data.get('action_type')
        user_ids = data.get('user_ids', [])
        reason = data.get('reason', '')

        if not action_type or not user_ids:
            return JsonResponse({'success': False, 'error': 'Action type and user IDs are required'}, status=400)

        users = User.objects.filter(id__in=user_ids)

        if not users.exists():
            return JsonResponse({'success': False, 'error': 'No valid users found'}, status=404)

        # Process based on action type
        if action_type == 'delete':
            # Maybe just mark as inactive instead of deleting
            for user in users:
                user.is_active = False
                user.save()
            message = f"Deactivated {users.count()} users"

        elif action_type == 'email':
            # Send email to all selected users
            for user in users:
                send_mail(
                    f"Important Message from {settings.SITE_NAME}",
                    reason or "This is an important notification from our team.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=True,
                )
            message = f"Email sent to {users.count()} users"

        elif action_type == 'upgrade':
            # Upgrade users to premium
            for user in users:
                user.is_premium = True
                user.save()
            message = f"Upgraded {users.count()} users to premium"

        elif action_type == 'downgrade':
            # Downgrade premium users
            for user in users:
                user.is_premium = False
                user.save()
            message = f"Downgraded {users.count()} users from premium"

        else:
            return JsonResponse({'success': False, 'error': 'Invalid action type'}, status=400)

        # You might want to log this admin action
        # AdminLog.objects.create(admin=request.user, action=action_type, details=f"Affected {users.count()} users")

        return JsonResponse({'success': True, 'message': message})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    




@admin_required
@require_POST
def bulk_user_action(request):
    try:
        data = json.loads(request.body)
        action_type = data.get('action_type')
        user_ids = data.get('user_ids', [])
        reason = data.get('reason', '')

        if not action_type or not user_ids:
            return JsonResponse({'success': False, 'error': 'Action type and user IDs are required'}, status=400)

        users = User.objects.filter(id__in=user_ids)

        if not users.exists():
            return JsonResponse({'success': False, 'error': 'No valid users found'}, status=404)

        # Process based on action type
        if action_type == 'activate':
            # Activate users
            count = 0
            for user in users:
                if not user.is_active:
                    user.is_active = True
                    user.save()
                    count += 1

                    # Log activity for the user
                    Activity.objects.create(
                        user=user,
                        type='admin_action',
                        description=f'Account activated by admin: {reason}'
                    )

            # Log admin activity
            log_admin_activity(
                request.admin_user,
                'bulk_activate',
                f'Activated {count} users: {reason}',
                request=request
            )

            message = f"Successfully activated {count} users"

        elif action_type == 'deactivate':
            # Deactivate users
            count = 0
            for user in users:
                if user.is_active:
                    user.is_active = False
                    user.save()
                    count += 1

                    # Log activity for the user
                    Activity.objects.create(
                        user=user,
                        type='admin_action',
                        description=f'Account deactivated by admin: {reason}'
                    )

            # Log admin activity
            log_admin_activity(
                request.admin_user,
                'bulk_deactivate',
                f'Deactivated {count} users: {reason}',
                request=request
            )

            message = f"Successfully deactivated {count} users"

        else:
            return JsonResponse({'success': False, 'error': 'Invalid action type'}, status=400)

        return JsonResponse({'success': True, 'message': message})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        import traceback
        print(f"Error in bulk_user_action: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)









@admin_required()
def admin_dashboard(request):
    """Main admin dashboard"""
    # Get user statistics - exclude admins and superusers
    User = get_user_model()
    total_users = User.objects.filter(is_staff=False, is_superuser=False).count()
    active_users = User.objects.filter(is_staff=False, is_superuser=False, is_active=True).count()

    # Get recent users - exclude admins and superusers
    recent_users = User.objects.filter(
        is_staff=False,
        is_superuser=False
    ).select_related('profile').order_by('-date_joined')[:5]

    # Revenue statistics
    total_revenue = PointsTransaction.objects.filter(
        payment_status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # AI generations count
    total_ai_generations = Activity.objects.filter(
        type__in=['cv_analysis', 'personal_statement_generation']
    ).count()

    # Recent activities - use timestamp instead of created_at
    recent_activity = AdminActivityLog.objects.order_by('-timestamp')[:10]

    context = {
        'total_users': total_users,
        'active_users': active_users,
        'recent_users': recent_users,
        'total_revenue': total_revenue,
        'total_ai_generations': total_ai_generations,
        'recent_activity': recent_activity,
        'admin_user': request.admin_user
    }

    return render(request, 'custom_admin/dashboard.html', context)




@admin_required('manage_users')
def user_management(request):
    """User management page"""
    # Get filter parameters
    search = request.GET.get('search', '')
    account_type = request.GET.get('account_type', '')
    is_paid = request.GET.get('is_paid', '')
    date_joined = request.GET.get('date_joined', '')

    # Base queryset - exclude admin and superuser accounts
    users = User.objects.filter(
        is_staff=False,
        is_superuser=False
    ).select_related('profile').prefetch_related('points')

    # Apply filters
    if search:
        users = users.filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )

    if account_type:
        users = users.filter(account_type=account_type)

    if is_paid:
        if is_paid == 'true':
            users = users.filter(profile__is_paid_user=True)
        else:
            users = users.filter(profile__is_paid_user=False)

    if date_joined:
        if date_joined == 'today':
            users = users.filter(date_joined__date=timezone.now().date())
        elif date_joined == 'week':
            week_ago = timezone.now() - timedelta(days=7)
            users = users.filter(date_joined__gte=week_ago)
        elif date_joined == 'month':
            month_ago = timezone.now() - timedelta(days=30)
            users = users.filter(date_joined__gte=month_ago)

    # Order by most recent
    users = users.order_by('-date_joined')

    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Calculate statistics - also exclude admins and superusers
    total_users = User.objects.filter(is_staff=False, is_superuser=False).count()
    paid_users = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        profile__is_paid_user=True
    ).count()
    new_users_today = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        date_joined__date=timezone.now().date()
    ).count()
    new_users_week = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        date_joined__gte=timezone.now() - timedelta(days=7)
    ).count()

    # Revenue statistics
    total_revenue = PointsTransaction.objects.filter(
        payment_status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    revenue_this_month = PointsTransaction.objects.filter(
        payment_status='completed',
        created_at__gte=timezone.now().replace(day=1)
    ).aggregate(total=Sum('amount'))['total'] or 0

    stats = {
        'total_users': total_users,
        'paid_users': paid_users,
        'free_users': total_users - paid_users,
        'new_users_today': new_users_today,
        'new_users_week': new_users_week,
        'total_revenue': total_revenue,
        'revenue_this_month': revenue_this_month,
        'conversion_rate': round((paid_users / total_users * 100), 1) if total_users > 0 else 0
    }

    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'account_type': account_type,
        'is_paid': is_paid,
        'date_joined': date_joined,
        'account_type_choices': User.ACCOUNT_TYPE_CHOICES if hasattr(User, 'ACCOUNT_TYPE_CHOICES') else [],
    }

    return render(request, 'custom_admin/user_management.html', context)






@admin_required('manage_users')
@require_http_methods(["POST"])
def update_user_points(request, user_id):
    """Update user points via AJAX"""
    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)
        points_to_add = int(data.get('points', 0))
        reason = data.get('reason', 'Admin adjustment')

        # Get or create user points
        user_points, created = UserPoints.objects.get_or_create(user=user)

        if points_to_add > 0:
            user_points.add_points(points_to_add)
            action = 'added'
        else:
            # For negative points, use absolute value
            points_to_remove = abs(points_to_add)
            if user_points.use_points(points_to_remove):
                action = 'removed'
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Insufficient points to remove'
                }, status=400)

        # Log admin activity
        log_admin_activity(
            request.admin_user,
            'update_user_points',
            f'{action.title()} {abs(points_to_add)} points for user {user.email}: {reason}',
            target_model='User',
            target_id=user.id,
            request=request
        )

        # Create user activity log
        Activity.objects.create(
            user=user,
            type='admin_action',
            description=f'Admin {action} {abs(points_to_add)} points: {reason}'
        )

        return JsonResponse({
            'success': True,
            'new_balance': user_points.balance,
            'message': f'Successfully {action} {abs(points_to_add)} points'
        })

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@admin_required('manage_users')
@require_http_methods(["POST"])
def toggle_user_status(request, user_id):
    """Toggle user active status"""
    try:
        user = User.objects.get(id=user_id)
        user.is_active = not user.is_active
        user.save()

        # Get the admin user from the request
        admin_user = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                admin_user = AdminUser.objects.get(user=request.user)
            except AdminUser.DoesNotExist:
                # If no AdminUser exists, just use the User object
                admin_user = request.user

        # Log admin activity - with error handling
        try:
            log_admin_activity(
                admin_user,
                'toggle_user_status',
                f'{"Activated" if user.is_active else "Deactivated"} user {user.email}',
                request=request
            )
        except Exception as log_error:
            # Log the error but don't fail the request
            print(f"Error logging admin activity: {str(log_error)}")

        # Create user activity log - with error handling
        try:
            Activity.objects.create(
                user=user,
                type='admin_action',
                description=f'Admin {"activated" if user.is_active else "deactivated"} account'
            )
        except Exception as activity_error:
            # Log the error but don't fail the request
            print(f"Error creating activity log: {str(activity_error)}")

        return JsonResponse({
            'success': True,
            'is_active': user.is_active,
            'message': f'User {"activated" if user.is_active else "deactivated"} successfully'
        })

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"Error in toggle_user_status: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    


@admin_required
@require_POST
def send_user_message(request, user_id):
    try:
        data = json.loads(request.body)
        subject = data.get('subject')
        message = data.get('message')

        if not subject or not message:
            return JsonResponse({'success': False, 'error': 'Subject and message are required'}, status=400)

        user = User.objects.get(id=user_id)

        # Send email to user
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )

        # You might want to log this message in your database
        # MessageLog.objects.create(user=user, subject=subject, message=message, sent_by=request.user)

        return JsonResponse({'success': True, 'message': f'Message sent to {user.email}'})

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@admin_required('manage_users')
def user_details(request, user_id):
    """Get detailed user information via AJAX"""
    try:
        user = User.objects.select_related('profile').get(id=user_id)

        # Get user points
        try:
            user_points = UserPoints.objects.get(user=user)
            points_balance = user_points.balance
            lifetime_points = user_points.lifetime_points
        except UserPoints.DoesNotExist:
            points_balance = 0
            lifetime_points = 0

        # Get recent transactions
        recent_transactions = PointsTransaction.objects.filter(
            user=user
        ).order_by('-created_at')[:5]

        # Get recent activities
        recent_activities = Activity.objects.filter(
            user=user
        ).order_by('-created_at')[:10]

        user_data = {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'date_joined': user.date_joined.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'is_active': user.is_active,
            'account_type': user.get_account_type_display() if hasattr(user, 'get_account_type_display') else 'N/A',
            'points_balance': points_balance,
            'lifetime_points': lifetime_points,
            'is_paid_user': user.profile.is_paid_user if hasattr(user, 'profile') else False,
            'recent_transactions': [
                {
                    'amount': float(t.amount),
                    'points': t.points,
                    'status': t.get_payment_status_display(),
                    'created_at': t.created_at.isoformat()
                } for t in recent_transactions
            ],
            'recent_activities': [
                {
                    'type': a.get_type_display() if hasattr(a, 'get_type_display') else a.type,
                    'description': a.description,
                    'created_at': a.created_at.isoformat()
                } for a in recent_activities
            ]
        }

        return JsonResponse({
            'success': True,
            'user': user_data
        })

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required('view_analytics')
def analytics(request):
    """Analytics dashboard with comprehensive metrics and visualizations"""
    # Get date range parameters
    today = timezone.now().date()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # Set date range with defaults
    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        except ValueError:
            date_from = today - timedelta(days=30)
    else:
        date_from = today - timedelta(days=30)

    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            date_to = today
    else:
        date_to = today

    # Calculate previous period for growth comparisons
    period_length = (date_to - date_from).days + 1
    prev_date_from = date_from - timedelta(days=period_length)
    prev_date_to = date_from - timedelta(days=1)

    # User statistics - exclude admins and superusers
    User = get_user_model()
    total_users = User.objects.filter(is_staff=False, is_superuser=False).count()

    # Active users (users with any activity in the period)
    active_users = Activity.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).values('user').distinct().count()

    # Active users in previous period
    prev_active_users = Activity.objects.filter(
        created_at__date__gte=prev_date_from,
        created_at__date__lte=prev_date_to
    ).values('user').distinct().count()

    # Calculate active user growth
    active_user_growth = round(((active_users - prev_active_users) / max(prev_active_users, 1)) * 100, 1)

    # New users in current period
    new_users = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        date_joined__date__gte=date_from,
        date_joined__date__lte=date_to
    ).count()

    # New users in previous period
    prev_new_users = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        date_joined__date__gte=prev_date_from,
        date_joined__date__lte=prev_date_to
    ).count()

    # Calculate user growth rate
    user_growth = round(((new_users - prev_new_users) / max(prev_new_users, 1)) * 100, 1)

    # Paid users
    paid_users = User.objects.filter(
        is_staff=False,
        is_superuser=False,
        profile__is_paid_user=True
    ).count()

    # Revenue statistics
    total_revenue = PointsTransaction.objects.filter(
        payment_status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Current period revenue
    period_revenue = PointsTransaction.objects.filter(
        payment_status='completed',
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Previous period revenue
    prev_period_revenue = PointsTransaction.objects.filter(
        payment_status='completed',
        created_at__date__gte=prev_date_from,
        created_at__date__lte=prev_date_to
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Calculate revenue growth rate
    revenue_growth = round(((period_revenue - prev_period_revenue) / max(prev_period_revenue, 1)) * 100, 1)

    # AI requests count
    ai_requests = Activity.objects.filter(
        type__in=['cv_analysis', 'personal_statement_generation'],
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).count()

    # Previous period AI requests
    prev_ai_requests = Activity.objects.filter(
        type__in=['cv_analysis', 'personal_statement_generation'],
        created_at__date__gte=prev_date_from,
        created_at__date__lte=prev_date_to
    ).count()

    # Calculate AI requests growth rate
    ai_requests_growth = round(((ai_requests - prev_ai_requests) / max(prev_ai_requests, 1)) * 100, 1)

    # Generate date range for charts
    date_range = []
    current_date = date_from
    while current_date <= date_to:
        date_range.append(current_date)
        current_date += timedelta(days=1)

    # Format dates for charts
    formatted_dates = [d.strftime('%b %d') for d in date_range]

    # User registration data
    user_reg_counts = []
    for date in date_range:
        count = User.objects.filter(
            is_staff=False,
            is_superuser=False,
            date_joined__date=date
        ).count()
        user_reg_counts.append(count)

    # Revenue data
    revenue_amounts = []
    for date in date_range:
        amount = PointsTransaction.objects.filter(
            payment_status='completed',
            created_at__date=date
        ).aggregate(total=Sum('amount'))['total'] or 0
        revenue_amounts.append(float(amount))

    # AI usage data
    cv_analysis_counts = []
    personal_statement_counts = []
    for date in date_range:
        cv_count = Activity.objects.filter(
            type='cv_analysis',
            created_at__date=date
        ).count()
        ps_count = Activity.objects.filter(
            type='personal_statement_generation',
            created_at__date=date
        ).count()
        cv_analysis_counts.append(cv_count)
        personal_statement_counts.append(ps_count)

    # Package distribution data
    # This assumes you have a way to track which package a user has purchased
    # Adjust according to your actual model structure
    try:
        package_data = PointsTransaction.objects.filter(
            payment_status='completed'
        ).values('package_name').annotate(count=Count('id')).order_by('-count')

        package_names = [item['package_name'] for item in package_data]
        package_counts = [item['count'] for item in package_data]
    except:
        # Fallback if package tracking is not available
        package_names = ['Basic', 'Standard', 'Premium']
        package_counts = [30, 50, 20]

    # Recent activities
    recent_activities = Activity.objects.select_related('user').order_by('-created_at')[:10]

    # Map activity types to action_type for template
    for activity in recent_activities:
        if activity.type in ['cv_analysis', 'personal_statement_generation']:
            activity.action_type = 'ai_request'
        elif activity.type in ['payment', 'purchase']:
            activity.action_type = 'payment'
        elif activity.type in ['login', 'logout']:
            activity.action_type = 'login'
        elif activity.type in ['document_upload', 'document_download']:
            activity.action_type = 'document'
        else:
            activity.action_type = 'other'

        # Set timestamp for template
        activity.timestamp = activity.created_at

    context = {
        'total_users': total_users,
        'active_users': active_users,
        'total_revenue': total_revenue,
        'ai_requests': ai_requests,
        'user_growth': user_growth,
        'active_user_growth': active_user_growth,
        'revenue_growth': revenue_growth,
        'ai_requests_growth': ai_requests_growth,
        'date_from': date_from,
        'date_to': date_to,
        'recent_activities': recent_activities,

        # Chart data (as JSON strings)
        'user_reg_dates': json.dumps(formatted_dates),
        'user_reg_counts': json.dumps(user_reg_counts),
        'revenue_dates': json.dumps(formatted_dates),
        'revenue_amounts': json.dumps(revenue_amounts),
        'ai_usage_dates': json.dumps(formatted_dates),
        'cv_analysis_counts': json.dumps(cv_analysis_counts),
        'personal_statement_counts': json.dumps(personal_statement_counts),
        'package_names': json.dumps(package_names),
        'package_counts': json.dumps(package_counts)
    }

    return render(request, 'custom_admin/analytics.html', context)






@admin_required('manage_admins')
def admin_management(request):
    """Manage admin users"""
    admins = AdminUser.objects.select_related('user').order_by('-created_at')

    context = {
        'admins': admins
    }

    return render(request, 'custom_admin/admin_management.html', context)





@admin_required()
def activity_logs(request):
    """View admin activity logs"""
    # The admin_user field is already a User model, so we don't need to select_related 'user'
    activities = AdminActivityLog.objects.order_by('-timestamp')

    # Pagination
    paginator = Paginator(activities, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj
    }

    return render(request, 'custom_admin/activity_logs.html', context)




def _recalculate_and_update_single_expert_rating(expert_id):
    """
    Recalculates and updates the average rating for a single expert.
    Saves the new rating to the Expert model.
    Returns True if successful or no change needed, False on error.
    """
    try:
        expert_to_update = Expert.objects.get(id=expert_id)
        
        # Calculate the new average rating from all *completed* consultations with a rating
        new_average_rating_data = Consultation.objects.filter(
            expert=expert_to_update,
            status='completed', 
            client_rating_for_expert__isnull=False 
        ).aggregate(avg_rating=Avg('client_rating_for_expert'))
        
        avg_rating_val = new_average_rating_data['avg_rating']
        
        # Convert to Decimal, default to 0.00, and quantize to 2 decimal places
        calculated_expert_rating = Decimal(str(avg_rating_val)) if avg_rating_val is not None else Decimal('0.00')
        calculated_expert_rating = calculated_expert_rating.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if expert_to_update.rating != calculated_expert_rating:
            old_rating = expert_to_update.rating
            expert_to_update.rating = calculated_expert_rating
            expert_to_update.save(update_fields=['rating'])
            logger.info(f"RATING_RECALC: Updated rating for expert {expert_to_update.full_name()} (ID: {expert_id}) from {old_rating} to {calculated_expert_rating:.2f}")
        # else:
            # logger.info(f"RATING_RECALC: Rating for expert {expert_to_update.full_name()} (ID: {expert_id}) is already {calculated_expert_rating:.2f}. No update needed.")
        return True
            
    except Expert.DoesNotExist:
        logger.error(f"RATING_RECALC: Expert with ID {expert_id} not found for rating update.")
        return False
    except Exception as e:
        logger.error(f"RATING_RECALC: Error updating rating for expert {expert_id}: {str(e)}", exc_info=True)
        return False





@admin_required('manage_experts')
def expert_management(request):
    all_expert_ids_for_rating_update = Expert.objects.values_list('id', flat=True)
    logger.info(f"EXPERT_MGMT_LOAD: Starting rating recalculation for {len(all_expert_ids_for_rating_update)} experts.")
    
    successful_recalcs = 0
    failed_recalcs = 0
    for expert_id_to_update in all_expert_ids_for_rating_update:
        if _recalculate_and_update_single_expert_rating(expert_id_to_update):
            successful_recalcs += 1
        else:
            failed_recalcs += 1
    
    if failed_recalcs > 0:
        logger.warning(f"EXPERT_MGMT_LOAD: Rating recalculation finished. Successful/NoChange: {successful_recalcs}, Failures: {failed_recalcs}.")
    else:
        logger.info(f"EXPERT_MGMT_LOAD: Rating recalculation finished for {successful_recalcs} experts.")

    search = request.GET.get('search', '')
    expertise_filter = request.GET.get('expertise', '') 
    status_filter = request.GET.get('status', '') 

    experts_query = Expert.objects.all()

    if search:
        experts_query = experts_query.filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(specialization__icontains=search) 
        )

    if expertise_filter:
        experts_query = experts_query.filter(expertise=expertise_filter)

    if status_filter:
        if status_filter == 'active':
            experts_query = experts_query.filter(is_active=True)
        elif status_filter == 'inactive': 
            experts_query = experts_query.filter(is_active=False)

    experts_query = experts_query.annotate(
        consultation_count_annotated=Count('expert_consultations', distinct=True), 
        review_count_annotated=Count(
            'expert_consultations', 
            filter=Q(expert_consultations__status='completed', expert_consultations__client_rating_for_expert__isnull=False), 
            distinct=True
        )
    ).order_by('-created_at')

    paginator = Paginator(experts_query, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_experts_count = Expert.objects.count()
    active_experts_count = Expert.objects.filter(is_active=True).count()
    total_consultations_count = Consultation.objects.filter(status='completed').count() 
    
    avg_rating_data = Expert.objects.filter(rating__gt=Decimal('0.00')).aggregate(avg=Avg('rating'))
    avg_rating_val = avg_rating_data['avg']
    avg_rating_all_experts_decimal = Decimal(str(avg_rating_val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if avg_rating_val is not None else Decimal('0.00')

    context = {
        'page_obj': page_obj,
        'total_experts': total_experts_count,
        'active_experts': active_experts_count,
        'total_consultations': total_consultations_count, 
        'avg_rating_all_experts': avg_rating_all_experts_decimal,
        'search': search,
        'expertise': expertise_filter,
        'status': status_filter,
        'expertise_choices': Expert.EXPERTISE_CHOICES if hasattr(Expert, 'EXPERTISE_CHOICES') else [], 
    }
    return render(request, 'custom_admin/expert_management.html', context)

@admin_required('manage_experts')
@require_http_methods(["POST"])
def add_expert(request):
    """Add a new expert and send them their credentials."""
    try:
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        email_address = request.POST.get('email')
        plain_password = request.POST.get('password')
        phone = request.POST.get('phone', '')
        expertise = request.POST.get('expertise')
        specialization = request.POST.get('specialization', '')
        bio = request.POST.get('bio', '')
        hourly_rate_str = request.POST.get('hourly_rate')
        is_active = request.POST.get('is_active') == '1' # Checkbox value '1' or None
        profile_image = request.FILES.get('profile_image')
        availability_json_string = request.POST.get('availability_json', '')

        if not all([first_name, last_name, email_address, plain_password, expertise, hourly_rate_str]):
            messages.error(request, "Missing required fields: First Name, Last Name, Email, Password, Expertise, Hourly Rate are all required.")
            return redirect('custom_admin:expert_management')

        try:
            hourly_rate = Decimal(hourly_rate_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except InvalidOperation:
            messages.error(request, "Invalid format for Hourly Rate.")
            return redirect('custom_admin:expert_management')

        if Expert.objects.filter(email=email_address).exists():
            messages.error(request, f"An expert with the email {email_address} already exists.")
            return redirect('custom_admin:expert_management')

        validated_availability_json = "[]"
        if availability_json_string.strip(): # Process only if not empty
            try:
                validated_availability_json = validate_availability_json_list_format(availability_json_string)
            except ValidationError as e:
                messages.error(request, f"Invalid availability JSON: {str(e)}")
                return redirect('custom_admin:expert_management')
        
        expert = Expert(
            first_name=first_name,
            last_name=last_name,
            email=email_address,
            phone=phone,
            expertise=expertise,
            specialization=specialization,
            bio=bio,
            hourly_rate=hourly_rate,
            is_active=is_active,
            availability_json=validated_availability_json
        )
        if profile_image:
            expert.profile_image = profile_image
        
        expert.set_password(plain_password) # Assumes Expert model has set_password
        expert.save()

        log_admin_activity(
            request.admin_user, 'add_expert',
            f'Added new expert: {expert.full_name}', # Assumes full_name method
            target_model='Expert', target_id=expert.id, request=request
        )
        messages.success(request, f'Expert {expert.full_name} added successfully.')

        try:
            subject = f"Welcome to {getattr(settings, 'PLATFORM_NAME', 'Our Platform')}! Your Expert Account Details"
            try:
                # Ensure 'expert_marketplace:expert_login' is a valid URL name
                login_url = build_absolute_uri(request, 'expert_marketplace:expert_login')
            except Exception:
                logger.warning("Could not reverse 'expert_marketplace:expert_login'. Falling back for login URL.")
                login_url = request.build_absolute_uri(getattr(settings, 'EXPERT_LOGIN_URL', '/experts/login/'))

            message_body = (
                f"Hi {expert.first_name},\n\n"
                f"An expert account has been created for you on {getattr(settings, 'PLATFORM_NAME', 'Our Platform')}.\n\n"
                f"You can log in using the following credentials:\n"
                f"Email: {expert.email}\n"
                f"Password: {plain_password}\n\n"
                f"Login here: {login_url}\n\n"
                f"We recommend changing your password after your first login for security.\n\n"
                f"Regards,\nThe {getattr(settings, 'PLATFORM_NAME', 'Our Platform')} Team"
            )
            send_mail(
                subject, message_body, settings.DEFAULT_FROM_EMAIL,
                [expert.email], fail_silently=False
            )
            messages.info(request, f"A welcome email with login details has been sent to {expert.email}.")
        except Exception as e:
            logger.error(f"Failed to send welcome email to {expert.email}: {str(e)}", exc_info=True)
            messages.warning(request, f"Expert {expert.full_name} added, but failed to send welcome email: {str(e)}")
        
        return redirect('custom_admin:expert_management')
        
    except Exception as e:
        logger.error(f"Error in add_expert view: {str(e)}", exc_info=True)
        messages.error(request, f'An unexpected error occurred while adding expert: {str(e)}')
        return redirect('custom_admin:expert_management')

@admin_required('manage_experts')
def expert_details(request, expert_id):
    """Fetch expert details for AJAX calls (e.g., populating modals)."""
    try:
        expert = get_object_or_404(Expert, id=expert_id)
        
        # Recalculate this specific expert's rating just in case it's needed fresh
        _recalculate_and_update_single_expert_rating(expert.id)
        expert.refresh_from_db(fields=['rating']) # Get the latest rating

        consultations = Consultation.objects.filter(expert=expert, status='completed').order_by('-scheduled_start_time')[:5]
        recent_consultations_data = [{
            'date': c.scheduled_start_time.strftime('%Y-%m-%d %H:%M') if c.scheduled_start_time else 'N/A',
            'client_name': c.user.get_full_name() if c.user and hasattr(c.user, 'get_full_name') else 'N/A', # Assumes client has get_full_name
            'type': c.get_consultation_type_display() if hasattr(c, 'get_consultation_type_display') else 'Consultation',
            'duration': c.duration_minutes if hasattr(c, 'duration_minutes') else None,
            'rating': float(c.client_rating_for_expert) if c.client_rating_for_expert is not None else None,
        } for c in consultations]

        data = {
            'success': True,
            'expert': {
                'id': expert.id,
                'first_name': expert.first_name,
                'last_name': expert.last_name,
                'full_name': expert.full_name,
                'email': expert.email,
                'phone': expert.phone,
                'expertise': expert.expertise,
                'expertise_display': expert.get_expertise_display() if hasattr(expert, 'get_expertise_display') else expert.expertise,
                'specialization': expert.specialization,
                'bio': expert.bio,
                'hourly_rate': float(expert.hourly_rate) if expert.hourly_rate is not None else None,
                'is_active': expert.is_active,
                'profile_image': expert.profile_image.url if expert.profile_image else None,
                'rating': float(expert.rating) if expert.rating is not None else 0.0,
                'review_count': Consultation.objects.filter(expert=expert, status='completed', client_rating_for_expert__isnull=False).count(),
                'consultation_count': Consultation.objects.filter(expert=expert).count(),
                'availability_json': expert.availability_json or "[]", # Ensure it's a string
                'recent_consultations': recent_consultations_data,
            }
        }
        return JsonResponse(data)
    except Exception as e:
        logger.error(f"Error fetching expert details for ID {expert_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required('manage_experts')
@require_http_methods(["POST"])
def update_expert(request, expert_id):
    expert = get_object_or_404(Expert, id=expert_id)
    try:
        expert.first_name = request.POST.get('first_name', expert.first_name)
        expert.last_name = request.POST.get('last_name', expert.last_name)
        expert.email = request.POST.get('email', expert.email) # Consider email uniqueness validation if changed
        expert.phone = request.POST.get('phone', expert.phone)
        expert.expertise = request.POST.get('expertise', expert.expertise)
        expert.specialization = request.POST.get('specialization', expert.specialization)
        expert.bio = request.POST.get('bio', expert.bio)
        
        hourly_rate_str = request.POST.get('hourly_rate')
        if hourly_rate_str:
            try:
                expert.hourly_rate = Decimal(hourly_rate_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except InvalidOperation:
                messages.error(request, "Invalid format for Hourly Rate.")
                return redirect('custom_admin:expert_management') # Or back to edit form

        expert.is_active = request.POST.get('is_active') == '1'

        if 'profile_image' in request.FILES:
            expert.profile_image = request.FILES['profile_image']
        
        new_password = request.POST.get('password')
        if new_password:
            expert.set_password(new_password) # Assumes Expert model has set_password

        availability_json_string = request.POST.get('availability_json', expert.availability_json)
        if availability_json_string.strip():
            try:
                expert.availability_json = validate_availability_json_list_format(availability_json_string)
            except ValidationError as e:
                messages.error(request, f"Invalid availability JSON: {str(e)}")
                return redirect('custom_admin:expert_management') # Or back to edit form
        else: # If string is empty, clear availability
            expert.availability_json = "[]"
            
        expert.save()
        
        # Recalculate rating after potential changes (though not directly edited here)
        _recalculate_and_update_single_expert_rating(expert.id)

        log_admin_activity(
            request.admin_user, 'update_expert',
            f'Updated expert: {expert.full_name}',
            target_model='Expert', target_id=expert.id, request=request
        )
        messages.success(request, f'Expert {expert.full_name} updated successfully.')
    except Exception as e:
        logger.error(f"Error updating expert {expert_id}: {str(e)}", exc_info=True)
        messages.error(request, f'Error updating expert: {str(e)}')
    return redirect('custom_admin:expert_management')

@admin_required('manage_experts')
@require_POST
def toggle_expert_status(request, expert_id):
    expert = get_object_or_404(Expert, id=expert_id)
    try:
        expert.is_active = not expert.is_active
        expert.save(update_fields=['is_active'])
        action = "activated" if expert.is_active else "deactivated"
        log_admin_activity(
            request.admin_user, 'toggle_expert_status',
            f'{action.capitalize()} expert: {expert.full_name}',
            target_model='Expert', target_id=expert.id, request=request
        )
        messages.success(request, f"Expert {expert.full_name} has been {action}.")
        return JsonResponse({'success': True, 'is_active': expert.is_active, 'message': f"Expert status changed to {action}."})
    except Exception as e:
        logger.error(f"Error toggling status for expert {expert_id}: {e}", exc_info=True)
        messages.error(request, "Failed to toggle expert status.")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@admin_required('manage_experts')
@require_POST
def update_expert_availability(request, expert_id):
    expert = get_object_or_404(Expert, id=expert_id)
    try:
        data = json.loads(request.body)
        availability_json_string = data.get('availability_json', '[]')

        validated_json = validate_availability_json_list_format(availability_json_string)
        expert.availability_json = validated_json
        expert.save(update_fields=['availability_json'])
        
        log_admin_activity(
            request.admin_user, 'update_expert_availability',
            f'Updated availability for expert: {expert.full_name}',
            target_model='Expert', target_id=expert.id, request=request
        )
        return JsonResponse({'success': True, 'message': 'Availability updated successfully.'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data.'}, status=400)
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error updating availability for expert {expert_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An unexpected error occurred.'}, status=500)



        
@admin_required('manage_experts')
def bulk_expert_action(request):
    """Perform bulk actions on experts"""
    try:
        data = json.loads(request.body)
        action_type = data.get('action_type')
        expert_ids = data.get('expert_ids', [])
        reason = data.get('reason', '')

        if not action_type or not expert_ids:
            return JsonResponse({'success': False, 'error': 'Action type and expert IDs are required'}, status=400)

        experts = Expert.objects.filter(id__in=expert_ids)

        if not experts.exists():
            return JsonResponse({'success': False, 'error': 'No valid experts found'}, status=404)

        # Process based on action type
        if action_type == 'activate':
            # Activate experts
            count = 0
            for expert in experts:
                if not expert.is_active:
                    expert.is_active = True
                    expert.save()
                    count += 1

            # Log admin activity
            log_admin_activity(
                request.admin_user,
                'bulk_activate_experts',
                f'Activated {count} experts: {reason}',
                request=request
            )

            message = f"Successfully activated {count} experts"

        elif action_type == 'deactivate':
            # Deactivate experts
            count = 0
            for expert in experts:
                if expert.is_active:
                    expert.is_active = False
                    expert.save()
                    count += 1

            # Log admin activity
            log_admin_activity(
                request.admin_user,
                'bulk_deactivate_experts',
                f'Deactivated {count} experts: {reason}',
                request=request
            )

            message = f"Successfully deactivated {count} experts"

        elif action_type == 'email':
            # Send email to all selected experts
            from django.core.mail import send_mail
            from django.conf import settings
            
            for expert in experts:
                send_mail(
                    f"Important Message from {settings.SITE_NAME}",
                    reason or "This is an important notification from our team.",
                    settings.DEFAULT_FROM_EMAIL,
                    [expert.email],
                    fail_silently=True,
                )
            
            # Log admin activity
            log_admin_activity(
                request.admin_user,
                'bulk_email_experts',
                f'Sent email to {experts.count()} experts: {reason}',
                request=request
            )
            
            message = f"Email sent to {experts.count()} experts"

        else:
            return JsonResponse({'success': False, 'error': 'Invalid action type'}, status=400)

        return JsonResponse({'success': True, 'message': message})

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        import traceback
        print(f"Error in bulk_expert_action: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



@admin_required('manage_referrals')
def referral_management_dashboard(request):
    """Dashboard for managing referrals showing all referrals with detailed information"""
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    status_filter = request.GET.get('status', '')
    sort_by = request.GET.get('sort', '-timestamp')
    
    # Base queryset with all necessary related objects
    referrals = ReferralSignup.objects.select_related(
        'referral_code', 
        'referral_code__user', 
        'referred_user'
    ).all()
    
    # Apply search filter
    if search_query:
        referrals = referrals.filter(
            Q(referral_code__code__icontains=search_query) | 
            Q(referral_code__user__email__icontains=search_query) |
            Q(referral_code__user__first_name__icontains=search_query) |
            Q(referral_code__user__last_name__icontains=search_query) |
            Q(referred_user__email__icontains=search_query) |
            Q(referred_user__first_name__icontains=search_query) |
            Q(referred_user__last_name__icontains=search_query)
        )
    
    # Apply status filter
    if status_filter == 'awarded':
        referrals = referrals.filter(points_awarded=True)
    elif status_filter == 'not_awarded':
        referrals = referrals.filter(points_awarded=False)
    elif status_filter == 'rewarded':
        referrals = referrals.filter(has_been_rewarded=True)
    elif status_filter == 'not_rewarded':
        referrals = referrals.filter(has_been_rewarded=False)
    
    # Apply date filters
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            referrals = referrals.filter(timestamp__date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            referrals = referrals.filter(timestamp__date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Apply sorting
    referrals = referrals.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(referrals, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get statistics
    total_referrals = ReferralSignup.objects.count()
    successful_referrals = ReferralSignup.objects.filter(points_awarded=True).count()
    conversion_rate = (successful_referrals / total_referrals * 100) if total_referrals > 0 else 0
    
    # Get top referrers - use a different name for the annotation
    top_referrers = ReferralCode.objects.annotate(
        successful_count=Count('signups', filter=Q(signups__points_awarded=True))
    ).filter(successful_count__gt=0).order_by('-successful_count')[:5]
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'total_referrals': total_referrals,
        'successful_referrals': successful_referrals,
        'conversion_rate': conversion_rate,
        'top_referrers': top_referrers,
    }
    
    return render(request, 'custom_admin/referrals/referral_management_dashboard.html', context)



@admin_required('manage_referrals')
def award_referral_points(request, signup_id):
    """Award points to a referral signup"""
    if request.method == 'POST':
        try:
            signup = ReferralSignup.objects.get(id=signup_id)
            signup.points_awarded = True
            signup.save()
            messages.success(request, f"Points awarded to referral {signup.id}")
        except ReferralSignup.DoesNotExist:
            messages.error(request, "Referral signup not found")
    
    return redirect('custom_admin:referral_management_dashboard')




@admin_required('manage_contacts')
def contact_messages_dashboard(request):
    """Dashboard for managing contact messages"""
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    sort_by = request.GET.get('sort', '-created_at')
    
    # Base queryset
    messages = ContactMessage.objects.all()
    
    # Apply search filter
    if search_query:
        messages = messages.filter(
            Q(name__icontains=search_query) | 
            Q(email__icontains=search_query) |
            Q(subject__icontains=search_query) |
            Q(message__icontains=search_query)
        )
    
    # Apply status filter
    if status_filter:
        messages = messages.filter(status=status_filter)
    
    # Apply date filters
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            messages = messages.filter(created_at__date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            messages = messages.filter(created_at__date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Apply sorting
    messages = messages.order_by(sort_by)
    
    # Get statistics
    total_messages = ContactMessage.objects.count()
    new_messages = ContactMessage.objects.filter(status='new').count()
    in_progress_messages = ContactMessage.objects.filter(status='in_progress').count()
    resolved_messages = ContactMessage.objects.filter(status='resolved').count()
    closed_messages = ContactMessage.objects.filter(status='closed').count()
    
    # Calculate resolution rate
    resolution_rate = (resolved_messages / total_messages * 100) if total_messages > 0 else 0
    
    # Pagination
    paginator = Paginator(messages, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'total_messages': total_messages,
        'new_messages': new_messages,
        'in_progress_messages': in_progress_messages,
        'resolved_messages': resolved_messages,
        'closed_messages': closed_messages,
        'resolution_rate': resolution_rate,
    }
    
    return render(request, 'custom_admin/contacts/contact_messages_dashboard.html', context)

@admin_required('manage_contacts')
def contact_message_detail(request, message_id):
    """View and update a contact message"""
    try:
        message = ContactMessage.objects.get(id=message_id)
    except ContactMessage.DoesNotExist:
        messages.error(request, "Message not found")
        return redirect('custom_admin:contact_messages_dashboard')
    
    if request.method == 'POST':
        status = request.POST.get('status')
        admin_notes = request.POST.get('admin_notes')
        
        if status:
            message.status = status
            if status == 'resolved' and message.status != 'resolved':
                message.resolved_at = timezone.now()
                message.resolved_by = request.user
            message.admin_notes = admin_notes
            message.save()
            messages.success(request, "Message updated successfully")
            
            # If user requested to go back to dashboard after saving
            if 'save_and_return' in request.POST:
                return redirect('custom_admin:contact_messages_dashboard')
            
            # Otherwise stay on the detail page
            return redirect('custom_admin:contact_message_detail', message_id=message_id)
    
    context = {
        'message': message,
    }
    
    return render(request, 'custom_admin/contacts/contact_message_detail.html', context)

@admin_required('manage_contacts')
def update_message_status(request, message_id):
    """AJAX endpoint to update message status"""
    if request.method == 'POST':
        try:
            message = ContactMessage.objects.get(id=message_id)
            status = request.POST.get('status')
            
            if status in dict(ContactMessage.STATUS_CHOICES).keys():
                message.status = status
                if status == 'resolved' and message.resolved_at is None:
                    message.resolved_at = timezone.now()
                    message.resolved_by = request.user
                message.save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid status'})
        except ContactMessage.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Message not found'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})



@admin_required('manage_consultations')
def consultation_management(request):
    """Consultation management dashboard"""
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    expertise_filter = request.GET.get('expertise', '')
    date_from_filter = request.GET.get('date_from', '')
    
    dispute_search_query = request.GET.get('dispute_search', '')
    dispute_status_filter = request.GET.get('dispute_status', '')
    dispute_type_filter = request.GET.get('dispute_type', '')
    
    bookings_list = Booking.objects.select_related('expert', 'user').order_by('-created_at') # Removed 'payment' for now
    
    if search:
        bookings_list = bookings_list.filter(
            Q(name__icontains=search) | # Booking's own name field
            Q(email__icontains=search) | # Booking's own email field
            Q(expert__first_name__icontains=search) | # Expert's direct first_name
            Q(expert__last_name__icontains=search) |  # Expert's direct last_name
            Q(expert__email__icontains=search) |      # Expert's direct email
            Q(user__email__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(id__icontains=search) # Search by booking ID
        ).distinct()
    
    if status_filter:
        bookings_list = bookings_list.filter(status=status_filter)
    
    if expertise_filter: # Assuming expertise_needed is the field on Booking
        bookings_list = bookings_list.filter(expertise_needed=expertise_filter) 
    
    if date_from_filter:
        try:
            date_from_obj = datetime.strptime(date_from_filter, '%Y-%m-%d').date()
            bookings_list = bookings_list.filter(scheduled_date__gte=date_from_obj)
        except ValueError:
            pass # Invalid date format
    
    disputes_list = NoShowDispute.objects.select_related(
        'booking', 'booking__expert', 'booking__user' # Simplified select_related
    ).order_by('-reported_at')

    if dispute_search_query:
        disputes_list = disputes_list.filter(
            Q(booking__user__email__icontains=dispute_search_query) |
            Q(booking__user__first_name__icontains=dispute_search_query) |
            Q(booking__user__last_name__icontains=dispute_search_query) |
            Q(booking__expert__first_name__icontains=dispute_search_query) | # Expert's direct name
            Q(booking__expert__last_name__icontains=dispute_search_query) |  # Expert's direct name
            Q(booking__expert__email__icontains=dispute_search_query) |      # Expert's direct email
            Q(id__icontains=dispute_search_query) | # Dispute ID
            Q(booking__id__icontains=dispute_search_query) | # Booking ID
            Q(reason__icontains=dispute_search_query)
        ).distinct()

    if dispute_status_filter:
        disputes_list = disputes_list.filter(status=dispute_status_filter)
    
    if dispute_type_filter:
        disputes_list = disputes_list.filter(dispute_type=dispute_type_filter)
    
    total_bookings = Booking.objects.count()
    pending_assignment = Booking.objects.filter(status='awaiting_assignment').count()
    completed_bookings = Booking.objects.filter(status='completed').count()
    active_disputes_count = NoShowDispute.objects.filter(status__in=['pending', 'expert_responded', 'investigating']).count()
    
    bookings_paginator = Paginator(bookings_list, 10)
    booking_page_number = request.GET.get('page') 
    page_obj = bookings_paginator.get_page(booking_page_number)

    disputes_paginator = Paginator(disputes_list, 10)
    dispute_page_number = request.GET.get('dispute_page')
    disputes_page_obj = disputes_paginator.get_page(dispute_page_number)
    
    context = {
        'page_obj': page_obj,
        'disputes_page_obj': disputes_page_obj,
        'search': search,
        'status': status_filter,
        'expertise': expertise_filter,
        'date_from': date_from_filter,
        'dispute_search': dispute_search_query,
        'dispute_status': dispute_status_filter,
        'dispute_type': dispute_type_filter,
        'total_bookings': total_bookings,
        'pending_assignment': pending_assignment,
        'completed_bookings': completed_bookings,
        'disputes_count': active_disputes_count,
        'status_choices': Booking.STATUS_CHOICES,
        'expertise_choices': Expert.EXPERTISE_CHOICES,
        'dispute_status_choices': NoShowDispute.STATUS_CHOICES, # For dispute filter dropdown
        'dispute_type_choices': NoShowDispute.DISPUTE_TYPE_CHOICES, # For dispute filter dropdown
    }
    return render(request, 'custom_admin/consultations/consultation_management.html', context)


@admin_required('manage_consultations')
def booking_details_api(request, booking_id):
    """API endpoint to get booking details for the modal."""
    try:
        # Removed 'expert__user', 'user__profile', 'payment' from select_related for now
        # as 'payment' is not on Booking model and 'user' on Expert can be null.
        booking = get_object_or_404(
            Booking.objects.select_related('user', 'expert'), 
            id=booking_id
        )

        client_name = booking.name or (booking.user.get_full_name() if booking.user and booking.user.get_full_name() else (booking.user.email if booking.user else 'N/A'))
        client_email = booking.email or (booking.user.email if booking.user else 'N/A')
        client_phone = booking.phone or (getattr(booking.user.profile, 'phone_number', 'N/A') if booking.user and hasattr(booking.user, 'profile') else 'N/A')

        expert_data = None
        if booking.expert:
            expert_data = {
                'id': booking.expert.id,
                'full_name': booking.expert.full_name, # Use Expert's full_name property
                'email': booking.expert.email, # Use Expert's direct email
                'phone': booking.expert.phone or 'N/A',
                'expertise_display': booking.expert.get_expertise_display(),
                'tier_display': booking.expert.get_tier_display(),
            }
        
        payment_info_data = None
        # Assuming Payment model has a ForeignKey to Booking named 'booking_payments' or similar if accessed via booking
        # For now, using direct fields from Booking model for payment info
        # If you have a separate Payment model linked to Booking, adjust this section
        payment_obj = None
        try:
            # Attempt to get related Payment object if it exists
            # This assumes Payment model has a OneToOneField to Booking named 'booking'
            # or Booking has a OneToOneField to Payment named 'payment_record' (less likely based on original code)
            # If Payment.booking is a ForeignKey, then it would be Payment.objects.get(booking=booking)
            if hasattr(booking, 'payment_record'): # Example if Booking has OneToOneField 'payment_record'
                 payment_obj = booking.payment_record
            else: # Fallback: try to find Payment by booking_id if Payment model has booking ForeignKey
                 payment_obj = Payment.objects.filter(booking_id=booking.id).first() # Adjust if Payment model has different relation

        except Payment.DoesNotExist:
            payment_obj = None
        except AttributeError: # If booking.payment_record doesn't exist
            payment_obj = None


        if payment_obj:
             payment_info_data = {
                'status_display': payment_obj.get_status_display(),
                'method': 'Stripe', 
                'transaction_id': payment_obj.stripe_payment_intent_id or booking.stripe_payment_intent_id or booking.stripe_charge_id or 'N/A',
                'date': payment_obj.updated_at.strftime('%b %d, %Y, %I:%M %p') if payment_obj.status == 'completed' else None,
                'amount': float(payment_obj.amount) if payment_obj.amount is not None else None,
            }
        elif booking.stripe_payment_intent_id or booking.stripe_charge_id: # If no separate Payment object, use Booking fields
            payment_info_data = {
                'status_display': booking.get_status_display(), # Booking status might reflect payment status
                'method': 'Stripe',
                'transaction_id': booking.stripe_payment_intent_id or booking.stripe_charge_id or 'N/A',
                'date': booking.updated_at.strftime('%b %d, %Y, %I:%M %p') if booking.status in ['confirmed', 'completed', 'refunded', 'partially_refunded'] else None, # Guessing date from booking update
                'amount': float(booking.consultation_fee) if booking.consultation_fee is not None else None,
            }


        data = {
            'id': booking.id,
            'status': booking.status,
            'status_display': booking.get_status_display(),
            'created_at': booking.created_at.isoformat(),
            'scheduled_date': booking.scheduled_date.isoformat() if booking.scheduled_date else None,
            'scheduled_time': booking.scheduled_time.strftime('%H:%M') if booking.scheduled_time else None,
            'duration_minutes': booking.duration_minutes,
            'expertise_needed_display': booking.get_expertise_needed_display() if booking.expertise_needed else 'N/A',
            'description': booking.description or 'No description provided.',
            'additional_notes': booking.additional_notes or 'No additional notes.',
            'consultation_fee': float(booking.consultation_fee) if booking.consultation_fee is not None else 0.0,
            'platform_fee': float(booking.platform_fee) if booking.platform_fee is not None else None,
            'expert_earnings': float(booking.expert_earnings) if booking.expert_earnings is not None else None,
            'stripe_payment_intent_id': booking.stripe_payment_intent_id,
            'stripe_charge_id': booking.stripe_charge_id, # Added this
            'user': {
                'full_name': client_name,
                'email': client_email,
                'phone': client_phone,
            },
            'expert': expert_data,
            'cancellation_reason': booking.cancellation_reason or None,
            'cancelled_at': booking.cancelled_at.isoformat() if booking.cancelled_at else None,
            'payment_info': payment_info_data,
        }
        return JsonResponse({'success': True, 'booking': data})
    except Exception as e:
        logger.error(f"Error in booking_details_api for booking_id {booking_id}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)


@admin_required('manage_consultations')
def available_experts_api(request, booking_id):
    """API endpoint to get available experts for a booking, matching expertise and search term."""
    try:
        booking = get_object_or_404(Booking, id=booking_id)
        search_term = request.GET.get('search', '')
        
        experts_query = Expert.objects.filter(is_active=True)
        
        if booking.expertise_needed:
            experts_query = experts_query.filter(expertise__iexact=booking.expertise_needed) # Use iexact for better match
        
        if search_term:
            experts_query = experts_query.filter(
                Q(first_name__icontains=search_term) | # Direct fields on Expert
                Q(last_name__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(expertise__icontains=search_term) | # Keep this if searching expertise names
                Q(specialization__icontains=search_term)
            ).distinct()
            
        experts_data = []
        for expert in experts_query[:50]: # Limit results
            experts_data.append({
                'id': expert.id,
                'full_name': expert.full_name, # Use Expert's property
                'email': expert.email, # Use Expert's direct email
                'expertise_display': expert.get_expertise_display(),
                'tier_display': expert.get_tier_display(),
            })
        
        return JsonResponse({'success': True, 'experts': experts_data})
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in available_experts_api for booking_id {booking_id}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)


@admin_required('manage_consultations')
@require_POST
def assign_expert(request, booking_id):
    """API endpoint to assign an expert to a booking"""
    try:
        data = json.loads(request.body)
        expert_id = data.get('expert_id')
        assignment_notes = data.get('assignment_notes', '') # Consider adding a field to Booking model for this
        notify_expert_flag = data.get('notify_expert', True) # Boolean from JSON

        booking = get_object_or_404(Booking.objects.select_related('user'), id=booking_id)
        
        if not expert_id:
            return JsonResponse({'success': False, 'error': 'Expert ID is required'}, status=400)
        
        expert = get_object_or_404(Expert, id=expert_id) # No need to select_related user for expert's own fields
        
        booking.expert = expert
        booking.status = 'confirmed'
        booking.assigned_at = timezone.now() # Set assigned_at timestamp
        # if assignment_notes: booking.admin_assignment_notes = assignment_notes # If field exists
        booking.save(update_fields=['expert', 'status', 'assigned_at']) # Be specific
        
        log_admin_activity(
            request.admin_user, 'assign_expert', 
            f'Assigned expert {expert.full_name} to booking #{booking.id}',
            target_model='Booking', target_id=booking.id, request=request
        )

        # Placeholder for notifications
        if notify_expert_flag:
            logger.info(f"Placeholder: Send expert assignment notification to {expert.email} for booking {booking.id}")
            # send_expert_assignment_notification(expert, booking)
        if booking.user: # Notify client if user exists
            logger.info(f"Placeholder: Send client expert assigned notification to {booking.user.email} for booking {booking.id}")
            # send_client_expert_assigned_notification(booking.user, booking)
        elif booking.email: # Notify guest client if email exists on booking
            logger.info(f"Placeholder: Send guest client expert assigned notification to {booking.email} for booking {booking.id}")


        return JsonResponse({
            'success': True,
            'message': f'Expert {expert.full_name} has been assigned to booking #{booking.id}.'
        })
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found.'}, status=404)
    except Expert.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Expert not found.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        logger.error(f"Error assigning expert to booking {booking_id}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)




# This view seems redundant if update_dispute_status handles all status changes.
# If it's specifically for booking status, it should be named clearly.
# For now, I'll assume it's for booking status.
@admin_required('manage_consultations')
@require_POST
def update_booking_status(request, booking_id): # This view was present in your file
    """API endpoint to update booking status"""
    try:
        data = json.loads(request.body)
        status = data.get('status')
        # notes = data.get('notes', '') # If you have a notes field on Booking for admin

        booking = get_object_or_404(Booking, id=booking_id)
        
        if not status or status not in [choice[0] for choice in Booking.STATUS_CHOICES]:
            return JsonResponse({'success': False, 'error': 'Valid status is required'}, status=400)
        
        booking.status = status
        # if notes:
        #     booking.admin_notes = notes # Example field
        booking.save()

        log_admin_activity(
            request.admin_user, 'update_booking_status', 
            f'Updated status for booking #{booking.id} to {booking.get_status_display()}',
            target_model='Booking', target_id=booking.id, request=request
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Booking status has been updated to {booking.get_status_display()}.'
        })
    except Booking.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Booking not found.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        logger.error(f"Error updating booking status for {booking_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)




@admin_required('manage_consultations')
def dispute_details(request, dispute_id):
    """Get dispute details AND its associated booking for the modal."""
    try:
        dispute = get_object_or_404(NoShowDispute.objects.select_related(
            'booking', 'booking__expert', 'booking__user', 'resolved_by' # Simplified
        ), id=dispute_id)
        
        booking = dispute.booking

        dispute_data = {
            'id': dispute.id,
            'status': dispute.status,
            'status_display': dispute.get_status_display(),
            'reported_at': dispute.reported_at.isoformat() if dispute.reported_at else None,
            'type_display': dispute.get_dispute_type_display(), 
            'reason': dispute.reason or 'No reason provided.',
            'expert_response': dispute.expert_response or 'No response yet.',
            'resolution_notes': dispute.resolution_notes or None,
            'resolved_at': dispute.resolved_at.isoformat() if dispute.resolved_at else None,
            'resolved_by': dispute.resolved_by.get_full_name() if dispute.resolved_by and hasattr(dispute.resolved_by, 'get_full_name') else (dispute.resolved_by.username if dispute.resolved_by else None),
            'refund_amount': float(dispute.refund_amount_decided) if dispute.refund_amount_decided is not None else None,
            'refund_processed': dispute.refund_processed_for_dispute, 
            'booking_consultation_fee': float(booking.consultation_fee) if booking.consultation_fee is not None else 0.0,
        }

        client_name = booking.name or (booking.user.get_full_name() if booking.user and booking.user.get_full_name() else (booking.user.email if booking.user else 'N/A'))
        client_email = booking.email or (booking.user.email if booking.user else 'N/A')
        client_phone = booking.phone # Assuming booking has phone, or get from user profile if exists

        expert_data_for_booking = None
        if booking.expert:
            expert_data_for_booking = {
                'full_name': booking.expert.full_name,
                'email': booking.expert.email,
                'expertise_display': booking.expert.get_expertise_display(),
            }

        booking_data = {
            'id': booking.id,
            'status': booking.status,
            'status_display': booking.get_status_display(),
            'created_at': booking.created_at.isoformat(),
            'scheduled_date': booking.scheduled_date.isoformat() if booking.scheduled_date else None,
            'scheduled_time': booking.scheduled_time.strftime('%H:%M') if booking.scheduled_time else None,
            'expertise_needed_display': booking.get_expertise_needed_display() if booking.expertise_needed else 'N/A',
            'consultation_fee': float(booking.consultation_fee) if booking.consultation_fee is not None else 0.0,
            'additional_notes': booking.additional_notes or 'No additional notes provided.',
            'user': {
                'full_name': client_name,
                'email': client_email,
                'phone': client_phone,
            },
            'expert': expert_data_for_booking,
        }
        
        return JsonResponse({'success': True, 'dispute': dispute_data, 'booking': booking_data})

    except NoShowDispute.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Dispute not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error in dispute_details API for dispute_id {dispute_id}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)











@admin_required('manage_consultations')
def get_dispute_by_booking_api(request, booking_id):
    """
    API endpoint to find if a dispute exists for a given booking ID.
    If multiple disputes exist, it returns the latest one based on reported_at.
    """
    try:
        dispute = NoShowDispute.objects.select_related(
            'booking', 'resolved_by'
        ).filter(booking_id=booking_id).order_by('-reported_at').first()

        if not dispute:
            return JsonResponse({'success': False, 'error': 'No dispute found for this booking.'}, status=404)

        dispute_data = {
            'id': dispute.id,
            'status': dispute.status,
            'status_display': dispute.get_status_display(),
            'reason': dispute.reason,
            'type_display': dispute.get_dispute_type_display(),
            'reported_at': dispute.reported_at.isoformat() if dispute.reported_at else None,
            'expert_response': dispute.expert_response,
            'resolution_notes': dispute.resolution_notes,
            'resolved_at': dispute.resolved_at.isoformat() if dispute.resolved_at else None,
            'resolved_by': dispute.resolved_by.get_full_name() if dispute.resolved_by else None,
            # Corrected field name below
            'refund_amount': float(dispute.refund_amount_decided) if dispute.refund_amount_decided is not None else None,
            # Corrected field name below
            'refund_processed': dispute.refund_processed_for_dispute,
            'booking_consultation_fee': float(dispute.booking.consultation_fee) if dispute.booking and dispute.booking.consultation_fee is not None else 0.0,
        }
        return JsonResponse({'success': True, 'dispute': dispute_data})

    except Exception as e: 
        logger.error(f"Error in get_dispute_by_booking_api for booking_id {booking_id}: {str(e)}")
        logger.error(traceback.format_exc()) 
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)


@admin_required('manage_consultations')
@require_POST
def update_dispute_status(request, dispute_id):
    """Update the status of a dispute and return the updated dispute."""
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status not in [choice[0] for choice in NoShowDispute.STATUS_CHOICES]:
            return JsonResponse({'success': False, 'error': 'Invalid status provided.'}, status=400)
        
        dispute = get_object_or_404(NoShowDispute.objects.select_related('booking', 'resolved_by'), id=dispute_id)
        
        if dispute.status == new_status: 
            return JsonResponse({'success': True, 'message': 'Status is already set to this value.', 'dispute': _serialize_dispute(dispute)})

        dispute.status = new_status
        if new_status == 'resolved' or new_status == 'rejected':
            if not dispute.resolved_at: 
                dispute.resolved_at = timezone.now()
                dispute.resolved_by = request.user 
        dispute.save()

        log_admin_activity(
            request.admin_user, 'update_dispute_status', 
            f'Updated status for dispute #{dispute.id} to {dispute.get_status_display()}',
            target_model='NoShowDispute', target_id=dispute.id, request=request
        )
        
        return JsonResponse({'success': True, 'dispute': _serialize_dispute(dispute)})
    except NoShowDispute.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Dispute not found.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        logger.error(f"Error updating dispute status for {dispute_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An internal server error occurred.'}, status=500)


@admin_required('manage_consultations')
@require_POST
def resolve_dispute(request, dispute_id):
    """Resolve a dispute with refund or rejection and return the updated dispute."""
    try:
        data = json.loads(request.body)
        action_type = data.get('resolution_action_type') 
        resolution_notes = data.get('resolution_notes')
        refund_amount_str = data.get('refund_amount')
        notify_parties = data.get('notify_parties', True) # Boolean from JSON
        
        dispute = get_object_or_404(NoShowDispute.objects.select_related(
            'booking', 'booking__expert', 'booking__user', 'resolved_by'
        ), id=dispute_id)
        
        booking_to_update = dispute.booking

        if not resolution_notes:
            return JsonResponse({'success': False, 'error': 'Resolution notes are required.'}, status=400)

        stripe_refund_attempted = False
        stripe_interaction_message = "Not Attempted"
        actual_stripe_refund_amount_this_op = Decimal('0.00')
        refund_service_response_dict = None 

        if action_type == 'resolved':
            dispute.status = 'resolved'
            try:
                intended_refund_for_dispute = Decimal(refund_amount_str if refund_amount_str else '0.00')
                if intended_refund_for_dispute < Decimal('0.00'):
                    return JsonResponse({'success': False, 'error': 'Refund amount cannot be negative.'}, status=400)
                
                dispute.refund_amount_decided = intended_refund_for_dispute 
                
                if intended_refund_for_dispute > Decimal('0.00'):
                    stripe_refund_attempted = True
                    if not booking_to_update.stripe_charge_id and not booking_to_update.stripe_payment_intent_id:
                        logger.error(f"Cannot process Stripe refund for dispute {dispute.id}. Booking {booking_to_update.id} has no Stripe charge or payment intent ID.")
                        stripe_interaction_message = "Booking has no payment charge or intent ID."
                        messages.error(request, f"Dispute resolved, but Stripe refund cannot be processed: {stripe_interaction_message}")
                        dispute.refund_processed_for_dispute = False # Explicitly False
                    else:
                        logger.info(f"Processing Stripe refund for dispute {dispute.id}, booking {booking_to_update.id}, amount {intended_refund_for_dispute}")
                        
                        op_success, service_resp_data_dict = process_stripe_refund(
                            booking=booking_to_update, 
                            amount_decimal=intended_refund_for_dispute,
                            reason_code='requested_by_customer', 
                            custom_reason_details=f"Dispute #{dispute.id} resolved by admin. Notes: {resolution_notes}"
                        )
                        refund_service_response_dict = service_resp_data_dict

                        if op_success:
                            stripe_status = service_resp_data_dict.get('stripe_status')
                            if stripe_status in ['succeeded', 'pending', 'already_refunded']:
                                dispute.refund_processed_for_dispute = True # Refund processed or pending
                                actual_stripe_refund_amount_this_op = Decimal(str(service_resp_data_dict.get('refund_amount', '0.00')))
                                booking_to_update.refund_amount = (booking_to_update.refund_amount or Decimal('0.00')) + actual_stripe_refund_amount_this_op
                                booking_to_update.stripe_refund_id = service_resp_data_dict.get('refund_id', booking_to_update.stripe_refund_id)
                                booking_to_update.refund_processed_at = timezone.now()
                                if booking_to_update.refund_amount >= booking_to_update.consultation_fee:
                                    booking_to_update.status = 'refunded'
                                else:
                                    booking_to_update.status = 'partially_refunded'
                                booking_to_update.save(update_fields=['refund_amount', 'stripe_refund_id', 'refund_processed_at', 'status'])
                            else: 
                                dispute.refund_processed_for_dispute = False # Refund not successfully processed
                                actual_stripe_refund_amount_this_op = Decimal('0.00')
                            
                            stripe_interaction_message = service_resp_data_dict.get('message', "Stripe interaction processed.")
                            logger.info(f"Stripe refund interaction for dispute {dispute.id}: {stripe_interaction_message}. Refund ID: {service_resp_data_dict.get('refund_id')}, Stripe Status: {stripe_status}")
                            messages.success(request, f"Dispute resolved. {stripe_interaction_message}")
                        else: 
                            dispute.refund_processed_for_dispute = False # Stripe call failed
                            stripe_interaction_message = str(service_resp_data_dict.get('error', 'Stripe refund failed.'))
                            logger.error(f"Stripe refund FAILED for dispute {dispute.id}. Error: {stripe_interaction_message}")
                            messages.error(request, f"Dispute resolved, but Stripe refund of £{intended_refund_for_dispute:.2f} FAILED: {stripe_interaction_message}")
                else: # This is the case for ZERO refund amount
                    dispute.refund_amount_decided = Decimal('0.00')
                    dispute.refund_processed_for_dispute = False # CORRECTED: Set to False, not None
                    stripe_interaction_message = "No refund amount specified (or zero amount entered) for this dispute resolution."
                    messages.success(request, "Dispute resolved with no refund.")
            
            except InvalidOperation:
                logger.error(f"Invalid refund amount format for dispute {dispute.id}: '{refund_amount_str}'")
                return JsonResponse({'success': False, 'error': 'Invalid refund amount format.'}, status=400)
        
        elif action_type == 'rejected':
            dispute.status = 'rejected'
            dispute.refund_amount_decided = None # Or Decimal('0.00') if you prefer
            dispute.refund_processed_for_dispute = False # CORRECTED: Set to False, not None
            stripe_interaction_message = "Dispute rejected, no refund processed."
            messages.success(request, "Dispute rejected.")
        
        else:
            return JsonResponse({'success': False, 'error': 'Invalid resolution action type.'}, status=400)
        
        dispute.resolution_notes = resolution_notes
        dispute.resolved_at = timezone.now()
        
        admin_user_for_log = request.admin_user if hasattr(request, 'admin_user') else request.user
        user_instance_for_resolved_by = None
        if hasattr(admin_user_for_log, 'user') and isinstance(admin_user_for_log.user, User):
            user_instance_for_resolved_by = admin_user_for_log.user
        elif isinstance(admin_user_for_log, User):
            user_instance_for_resolved_by = admin_user_for_log
        
        if user_instance_for_resolved_by:
            dispute.resolved_by = user_instance_for_resolved_by
        else:
            logger.warning(f"Could not identify a valid User instance for dispute {dispute.id}.resolved_by. Admin user: {admin_user_for_log}")

        # The error occurs here if refund_processed_for_dispute is None
        dispute.save() 

        log_admin_activity(
            admin_user_for_log, 
            'resolve_dispute', 
            f'{action_type.capitalize()} dispute #{dispute.id}. Notes: {resolution_notes}. Stripe Interaction: {stripe_interaction_message}',
            target_model='NoShowDispute', target_id=dispute.id, request=request
        )
        
        if notify_parties:
            _send_dispute_resolution_emails_updated(dispute) 
        
        final_operation_success = True
        # If Stripe refund was attempted but not marked as processed (e.g., Stripe call failed)
        if stripe_refund_attempted and not dispute.refund_processed_for_dispute:
            # Check if the refund_service_response_dict indicates a failure from Stripe's side
            if refund_service_response_dict and not refund_service_response_dict.get('success', False):
                 final_operation_success = False

        json_response_message = f"Dispute has been {action_type}."
        if stripe_refund_attempted: 
            json_response_message += f" Stripe Interaction: {stripe_interaction_message}"
        
        return JsonResponse({
            'success': final_operation_success, 
            'message': json_response_message,
            'dispute': _serialize_dispute(dispute)
        }, status=200 if final_operation_success else 400)

    except NoShowDispute.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Dispute not found.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data.'}, status=400)
    except Exception as e:
        logger.error(f"Error resolving dispute {dispute_id}: {str(e)}", exc_info=True)
        # Print traceback to console for immediate debugging during development
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'An internal server error occurred: {str(e)}'}, status=500)
    



def _serialize_dispute(dispute):
    """Helper function to serialize a dispute object for API responses."""
    return {
        'id': dispute.id,
        'status': dispute.status,
        'status_display': dispute.get_status_display(),
        'reported_at': dispute.reported_at.isoformat() if dispute.reported_at else None,
        'type_display': dispute.get_dispute_type_display(),
        'reason': dispute.reason,
        'expert_response': dispute.expert_response,
        'resolution_notes': dispute.resolution_notes,
        'resolved_at': dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        'resolved_by': dispute.resolved_by.get_full_name() if dispute.resolved_by else None,
        # Corrected field name below
        'refund_amount': float(dispute.refund_amount_decided) if dispute.refund_amount_decided is not None else None,
        # Corrected field name below
        'refund_processed': dispute.refund_processed_for_dispute,
        'booking_consultation_fee': float(dispute.booking.consultation_fee) if dispute.booking and dispute.booking.consultation_fee is not None else 0.0,
        'booking_id': dispute.booking_id,
    }



def _send_dispute_resolution_emails_updated(dispute):
    """Sends dispute resolution emails to client and expert."""
    booking = dispute.booking
    client_email_address = booking.user.email if booking.user and hasattr(booking.user, 'email') else booking.email
    
    expert_email_address = None
    if booking.expert:
        if hasattr(booking.expert, 'user') and booking.expert.user and hasattr(booking.expert.user, 'email'):
            expert_email_address = booking.expert.user.email
        elif hasattr(booking.expert, 'email'): # Fallback if expert model has direct email field
            expert_email_address = booking.expert.email


    subject_base = f"Update on Your Dispute for Booking #{booking.id}"
    if dispute.status == 'resolved':
        subject = subject_base + " - Resolved"
    elif dispute.status == 'rejected':
        subject = subject_base + " - Decision Reached"
    else: 
        subject = subject_base 

    # Determine client name
    client_name_to_display = "Client" # Default
    if booking.user:
        if hasattr(booking.user, 'get_full_name') and booking.user.get_full_name():
            client_name_to_display = booking.user.get_full_name()
        elif hasattr(booking.user, 'first_name') and booking.user.first_name:
            client_name_to_display = booking.user.first_name
        elif hasattr(booking.user, 'username'):
            client_name_to_display = booking.user.username
    elif booking.name: # Fallback to name on booking
        client_name_to_display = booking.name

    # Determine expert name
    expert_name_to_display = "Expert" # Default
    if booking.expert:
        if hasattr(booking.expert, 'user') and booking.expert.user:
            if hasattr(booking.expert.user, 'get_full_name') and booking.expert.user.get_full_name():
                expert_name_to_display = booking.expert.user.get_full_name()
            elif hasattr(booking.expert.user, 'first_name') and booking.expert.user.first_name:
                expert_name_to_display = booking.expert.user.first_name
            elif hasattr(booking.expert.user, 'username'):
                 expert_name_to_display = booking.expert.user.username
        elif hasattr(booking.expert, 'full_name') and booking.expert.full_name: # Fallback to full_name on Expert model
            expert_name_to_display = booking.expert.full_name
        elif hasattr(booking.expert, 'first_name') and booking.expert.first_name: # Fallback to first_name on Expert model
            expert_name_to_display = booking.expert.first_name


    # Client Email
    if client_email_address:
        client_context = {
            'dispute': dispute,  # <-- CRUCIAL FIX: Pass the whole dispute object
            'client_name': client_name_to_display,
            'platform_name': getattr(settings, 'PLATFORM_NAME', settings.SITE_NAME), # Use PLATFORM_NAME or SITE_NAME
            # The templates will now use:
            # {{ dispute.booking.id }} instead of {{ booking_id }}
            # {{ dispute.get_status_display }} instead of {{ dispute_status_display }}
            # {{ dispute.resolution_notes }}
            # {{ dispute.refund_amount }}
        }
        client_html_message = render_to_string('emails/dispute_resolution_client.html', client_context)
        client_plain_message = strip_tags(client_html_message)
        try:
            send_mail(subject, client_plain_message, settings.DEFAULT_FROM_EMAIL, [client_email_address], html_message=client_html_message)
            logger.info(f"Dispute resolution email sent to client {client_email_address} for dispute {dispute.id}")
        except Exception as e:
            logger.error(f"Failed to send dispute resolution email to client {client_email_address} for dispute {dispute.id}: {e}", exc_info=True)

    # Expert Email
    if expert_email_address:
        expert_context = {
            'dispute': dispute,  # <-- CRUCIAL FIX: Pass the whole dispute object
            'expert_name': expert_name_to_display,
            'client_name': client_name_to_display, # Expert template might want to show client's name
            'platform_name': getattr(settings, 'PLATFORM_NAME', settings.SITE_NAME),
        }
        expert_html_message = render_to_string('emails/dispute_resolution_expert.html', expert_context)
        expert_plain_message = strip_tags(expert_html_message)
        try:
            send_mail(subject, expert_plain_message, settings.DEFAULT_FROM_EMAIL, [expert_email_address], html_message=expert_html_message)
            logger.info(f"Dispute resolution email sent to expert {expert_email_address} for dispute {dispute.id}")
        except Exception as e:
            logger.error(f"Failed to send dispute resolution email to expert {expert_email_address} for dispute {dispute.id}: {e}", exc_info=True)






@admin_required('manage_payouts') 
def payout_management_view(request):
    """Manage expert earnings and bonus payouts."""
    
    earning_expert_search = request.GET.get('earning_expert_search', '')
    earning_status_filter = request.GET.get('earning_status', '')
    earning_date_from = request.GET.get('earning_date_from', '')
    earning_date_to = request.GET.get('earning_date_to', '')

    bonus_expert_search = request.GET.get('bonus_expert_search', '')
    bonus_status_filter = request.GET.get('bonus_status', '')
    bonus_date_from = request.GET.get('bonus_date_from', '')
    bonus_date_to = request.GET.get('bonus_date_to', '')

    expert_earnings_query = ExpertEarning.objects.select_related('expert__user', 'booking').order_by('-calculated_at')
    if earning_expert_search:
        expert_earnings_query = expert_earnings_query.filter(
            Q(expert__user__first_name__icontains=earning_expert_search) | # Assuming Expert links to User
            Q(expert__user__last_name__icontains=earning_expert_search) |
            Q(expert__user__email__icontains=earning_expert_search)
        )
    if earning_status_filter:
        expert_earnings_query = expert_earnings_query.filter(status=earning_status_filter)
    if earning_date_from:
        expert_earnings_query = expert_earnings_query.filter(calculated_at__date__gte=earning_date_from)
    if earning_date_to:
        expert_earnings_query = expert_earnings_query.filter(calculated_at__date__lte=earning_date_to)

    expert_bonuses_query = ExpertBonus.objects.select_related('expert__user').order_by('-created_at')
    if bonus_expert_search:
        expert_bonuses_query = expert_bonuses_query.filter(
            Q(expert__user__first_name__icontains=bonus_expert_search) |
            Q(expert__user__last_name__icontains=bonus_expert_search) |
            Q(expert__user__email__icontains=bonus_expert_search)
        )
    if bonus_status_filter:
        expert_bonuses_query = expert_bonuses_query.filter(status=bonus_status_filter)
    if bonus_date_from:
        expert_bonuses_query = expert_bonuses_query.filter(created_at__date__gte=bonus_date_from)
    if bonus_date_to:
        expert_bonuses_query = expert_bonuses_query.filter(created_at__date__lte=bonus_date_to)

    earnings_paginator = Paginator(expert_earnings_query, 15)
    earnings_page_number = request.GET.get('earnings_page')
    earnings_page_obj = earnings_paginator.get_page(earnings_page_number)

    bonuses_paginator = Paginator(expert_bonuses_query, 15)
    bonuses_page_number = request.GET.get('bonuses_page')
    bonuses_page_obj = bonuses_paginator.get_page(bonuses_page_number)
    
    total_pending_earnings = expert_earnings_query.filter(status=ExpertEarning.PENDING).aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    total_paid_earnings = expert_earnings_query.filter(status=ExpertEarning.PAID).aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    total_failed_earnings = expert_earnings_query.filter(status=ExpertEarning.FAILED).count()

    total_pending_bonuses = expert_bonuses_query.filter(status=ExpertBonus.PENDING).aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    total_paid_bonuses = expert_bonuses_query.filter(status=ExpertBonus.PAID).aggregate(total=Coalesce(Sum('amount'), Decimal(0)))['total']
    total_failed_bonuses = expert_bonuses_query.filter(status=ExpertBonus.FAILED).count()

    overall_pending_payout = total_pending_earnings + total_pending_bonuses

    context = {
        'earnings_page_obj': earnings_page_obj,
        'bonuses_page_obj': bonuses_page_obj,
        
        # For the dropdown fix:
        'earning_status_choices_json': json.dumps(list(ExpertEarning.STATUS_CHOICES)),
        'bonus_status_choices_json': json.dumps(list(ExpertBonus.STATUS_CHOICES)),
        
        # For direct use in template logic (Pay/Retry button condition)
        'ExpertEarning_PENDING': ExpertEarning.PENDING,
        'ExpertEarning_FAILED': ExpertEarning.FAILED,
        'ExpertBonus_PENDING': ExpertBonus.PENDING,
        'ExpertBonus_FAILED': ExpertBonus.FAILED,

        # Keep original choices for filter dropdowns if they are different or simpler
        'earning_status_choices': ExpertEarning.STATUS_CHOICES, 
        'bonus_status_choices': ExpertBonus.STATUS_CHOICES,

        'filters': { 
            'earning_expert_search': earning_expert_search,
            'earning_status_filter': earning_status_filter,
            'earning_date_from': earning_date_from,
            'earning_date_to': earning_date_to,
            'bonus_expert_search': bonus_expert_search,
            'bonus_status_filter': bonus_status_filter,
            'bonus_date_from': bonus_date_from,
            'bonus_date_to': bonus_date_to,
        },
        'stats': {
            'total_pending_earnings': total_pending_earnings,
            'total_paid_earnings': total_paid_earnings,
            'total_failed_earnings': total_failed_earnings,
            'total_pending_bonuses': total_pending_bonuses,
            'total_paid_bonuses': total_paid_bonuses,
            'total_failed_bonuses': total_failed_bonuses,
            'overall_pending_payout': overall_pending_payout,
        },
        'page_title': 'Payout Management',
        'page_description': 'Oversee and manage expert earnings and bonus payouts.'
    }
    return render(request, 'custom_admin/payouts/payout_management.html', context)




@admin_required('manage_payouts') 
@require_POST
def initiate_earning_payout_api(request, earning_id):
    try:
        # Ensure expert has a Stripe account ID and it's active. Adjust field names if necessary.
        earning = get_object_or_404(ExpertEarning.objects.select_related('expert', 'expert__user'), 
                                    id=earning_id)

        if not (earning.expert.stripe_account_id and earning.expert.stripe_account_active):
            return JsonResponse({'success': False, 'error': 'Expert Stripe account is not configured or inactive.'}, status=400)

        if earning.status not in [ExpertEarning.PENDING, ExpertEarning.FAILED]:
            return JsonResponse({'success': False, 'error': 'Payout can only be initiated for pending or failed earnings.'}, status=400)

        # --- START STRIPE PAYOUT LOGIC (Placeholder) ---
        # In a real scenario:
        # 1. Initialize Stripe API
        # 2. Create a Stripe Transfer to the expert's connected account:
        #    stripe.Transfer.create(
        #        amount=int(earning.amount * 100),  # Amount in cents
        #        currency="gbp", # Or your platform's currency
        #        destination=earning.expert.stripe_account_id,
        #        transfer_group="CONSULTATION_PAYOUTS", # Optional
        #        metadata={'earning_id': earning.id, 'expert_id': earning.expert.id}
        #    )
        # 3. Handle success:
        #    earning.status = ExpertEarning.PAID # Or 'processing' if transfer is async
        #    earning.paid_at = timezone.now()
        #    earning.transaction_id = stripe_transfer_object.id # Store Stripe transfer ID
        #    earning.notes = f"Payout of £{earning.amount} initiated via Stripe by admin {request.admin_user.email}."
        #    earning.save()
        #    log_admin_activity(request.admin_user, 'initiate_earning_payout_success', f'Successfully initiated payout for earning ID {earning.id}. Stripe TXN: {stripe_transfer_object.id}', request=request)
        #    return JsonResponse({'success': True, 'message': f'Stripe payout for earning ID {earning.id} initiated successfully (simulation).'})
        # 4. Handle Stripe errors (API errors, card errors on Stripe's side for payouts if applicable, etc.):
        #    earning.status = ExpertEarning.FAILED
        #    earning.notes = f"Stripe payout attempt failed: {e.user_message or str(e)}" # Store Stripe error
        #    earning.save()
        #    log_admin_activity(request.admin_user, 'initiate_earning_payout_failed', f'Stripe payout failed for earning ID {earning.id}: {str(e)}', request=request)
        #    return JsonResponse({'success': False, 'error': f'Stripe payout failed (simulation): {str(e)}'})
        # --- END STRIPE PAYOUT LOGIC (Placeholder) ---

        # Current Simulation:
        logger.info(f"Admin {request.admin_user.email if hasattr(request.admin_user, 'email') else request.admin_user.username} SIMULATING payout for earning ID {earning.id} for expert {earning.expert.user.email} amount £{earning.amount}")
        
        # Simulate changing status for demo purposes (remove if you want it to stay pending until real integration)
        # earning.status = ExpertEarning.PAID # Or a new 'PROCESSING' status
        # earning.paid_at = timezone.now()
        # earning.transaction_id = f"SIM_TXN_{earning.id}"
        # earning.notes = f"Payout of £{earning.amount} simulated by admin {request.admin_user.email}."
        # earning.save()

        log_admin_activity(request.admin_user, 'initiate_earning_payout_attempt', f'Attempted to initiate payout for earning ID {earning.id}. (Stripe integration pending)', request=request)
        messages.success(request, f"Payout initiation for Earning ID {earning.id} (Expert: {earning.expert.user.email}, Amount: £{earning.amount}) has been logged. Actual Stripe payout is pending implementation.")
        
        return JsonResponse({'success': True, 'message': f'Payout initiation for Earning ID {earning.id} logged. Actual Stripe payout pending implementation.'})

    except Expert.DoesNotExist: # Catch if expert related to earning is somehow missing
        return JsonResponse({'success': False, 'error': 'Associated expert not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error initiating earning payout for ID {earning_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'}, status=500)


@admin_required('manage_payouts')
@require_POST
def initiate_bonus_payout_api(request, bonus_id):
    try:
        bonus = get_object_or_404(ExpertBonus.objects.select_related('expert', 'expert__user'), 
                                  id=bonus_id)

        if not (bonus.expert.stripe_account_id and bonus.expert.stripe_account_active):
            return JsonResponse({'success': False, 'error': 'Expert Stripe account is not configured or inactive.'}, status=400)

        if bonus.status not in [ExpertBonus.PENDING, ExpertBonus.FAILED]:
            return JsonResponse({'success': False, 'error': 'Payout can only be initiated for pending or failed bonuses.'}, status=400)

        # --- STRIPE PAYOUT LOGIC (Placeholder - similar to earnings) ---
        logger.info(f"Admin {request.admin_user.email if hasattr(request.admin_user, 'email') else request.admin_user.username} SIMULATING payout for bonus ID {bonus.id} for expert {bonus.expert.user.email} amount £{bonus.amount}")
        
        log_admin_activity(request.admin_user, 'initiate_bonus_payout_attempt', f'Attempted to initiate payout for bonus ID {bonus.id}. (Stripe integration pending)', request=request)
        messages.success(request, f"Payout initiation for Bonus ID {bonus.id} (Expert: {bonus.expert.user.email}, Amount: £{bonus.amount}) has been logged. Actual Stripe payout is pending implementation.")
        
        return JsonResponse({'success': True, 'message': f'Payout initiation for Bonus ID {bonus.id} logged. Actual Stripe payout pending implementation.'})

    except Expert.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Associated expert not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error initiating bonus payout for ID {bonus_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'}, status=500)


@admin_required('manage_payouts')
@require_POST
def update_earning_payout_status_api(request, earning_id):
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        notes = data.get('notes', None)
        transaction_id = data.get('transaction_id', None)

        earning = get_object_or_404(ExpertEarning, id=earning_id)
        
        if new_status not in [s[0] for s in ExpertEarning.STATUS_CHOICES]:
            return JsonResponse({'success': False, 'error': 'Invalid status provided.'}, status=400)

        old_status = earning.status
        earning.status = new_status
        
        if notes is not None: # Allow clearing notes with empty string
            earning.notes = notes
        if transaction_id is not None: # Allow clearing transaction_id
            earning.transaction_id = transaction_id

        if new_status == ExpertEarning.PAID and old_status != ExpertEarning.PAID:
            earning.paid_at = timezone.now()
            # Potentially update expert's total_earnings_paid and pending_payout here
            # This requires careful handling to avoid double counting if Stripe also updates it
            # For manual marking, this might be appropriate.
        elif old_status == ExpertEarning.PAID and new_status != ExpertEarning.PAID:
            earning.paid_at = None # Clear paid_at if moving away from PAID status

        earning.save()
        log_admin_activity(request.admin_user, 'update_earning_status', f'Updated earning ID {earning.id} status to {new_status}. Notes: {notes or "N/A"}', request=request)
        return JsonResponse({'success': True, 'message': 'Earning payout status updated.'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
    except ExpertEarning.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Earning record not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error updating earning payout status: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@admin_required('manage_payouts')
@require_POST
def update_bonus_payout_status_api(request, bonus_id):
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        notes = data.get('notes', None)
        transaction_id = data.get('transaction_id', None)

        bonus = get_object_or_404(ExpertBonus, id=bonus_id)

        if new_status not in [s[0] for s in ExpertBonus.STATUS_CHOICES]:
            return JsonResponse({'success': False, 'error': 'Invalid status provided.'}, status=400)

        old_status = bonus.status
        bonus.status = new_status

        if notes is not None:
            bonus.notes = notes
        if transaction_id is not None:
            bonus.transaction_id = transaction_id
            
        if new_status == ExpertBonus.PAID and old_status != ExpertBonus.PAID:
            bonus.paid_at = timezone.now()
        elif old_status == ExpertBonus.PAID and new_status != ExpertBonus.PAID:
            bonus.paid_at = None

        bonus.save()
        log_admin_activity(request.admin_user, 'update_bonus_status', f'Updated bonus ID {bonus.id} status to {new_status}. Notes: {notes or "N/A"}', request=request)
        return JsonResponse({'success': True, 'message': 'Bonus payout status updated.'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
    except ExpertBonus.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Bonus record not found.'}, status=404)
    except Exception as e:
        logger.error(f"Error updating bonus payout status: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)