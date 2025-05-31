from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse, FileResponse
from .models import UserPoints
import logging

logger = logging.getLogger(__name__)

# In points_utils.py
def require_points(points_required):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Skip check for staff/admin users
            if request.user.is_staff or request.user.is_superuser:
                # Add points_required to kwargs so the view can use it
                kwargs['points_required'] = points_required
                return view_func(request, *args, **kwargs)

            # Check if user has enough points
            try:
                user_points = UserPoints.objects.get(user=request.user)

                # Update paid status based on points balance
                try:
                    profile = request.user.profile
                    if user_points.balance <= 0 and profile.is_paid_user:
                        profile.is_paid_user = False
                        profile.save()
                        logger.info(f"User {request.user.username} is out of points, updated to non-paid status")
                    elif user_points.balance > 0 and not profile.is_paid_user:
                        profile.is_paid_user = True
                        profile.save()
                        logger.info(f"User {request.user.username} has points, updated to paid status")
                except Exception as e:
                    logger.error(f"Error updating paid status: {str(e)}")

                if user_points.balance < points_required:
                    # ALWAYS return JSON for POST requests (assuming they're AJAX)
                    if request.method == 'POST':
                        return JsonResponse({
                            'error': f'You need {points_required} AI points for this action. You currently have {user_points.balance} points.',
                            'error_type': 'insufficient_points',
                            'current_points': user_points.balance,
                            'required_points': points_required
                        }, status=402)  # 402 Payment Required

                    # Redirect to purchase page for regular GET requests
                    messages.error(request, f'You need {points_required} AI points for this action. You currently have {user_points.balance} points.')
                    return redirect('document_manager:purchase_points')

                # Add points_required to kwargs so the view can use it
                kwargs['points_required'] = points_required
                return view_func(request, *args, **kwargs)

            except UserPoints.DoesNotExist:
                # Create user points record if it doesn't exist
                UserPoints.objects.create(user=request.user, balance=0)

                # Update paid status
                try:
                    profile = request.user.profile
                    profile.is_paid_user = False
                    profile.save()
                except Exception as e:
                    logger.error(f"Error updating paid status: {str(e)}")

                # ALWAYS return JSON for POST requests (assuming they're AJAX)
                if request.method == 'POST':
                    return JsonResponse({
                        'error': f'You need {points_required} AI points for this action. You currently have 0 points.',
                        'error_type': 'insufficient_points',
                        'current_points': 0,
                        'required_points': points_required
                    }, status=402)

                messages.error(request, f'You need {points_required} AI points for this action. You currently have 0 points.')
                return redirect('document_manager:purchase_points')

        return _wrapped_view
    return decorator