# document_manager/points_utils.py
from functools import wraps
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse # If you use reverse for login URL

from .models import UserPoints
# UserProfile is accessed via request.user.profile
# from accounts.models import UserProfile
import logging

logger = logging.getLogger(__name__)

# The get_referral_points function is removed as its logic is superseded by available_free_uses

def require_points(points_cost_arg):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest': # AJAX
                    return JsonResponse({'error': 'Authentication required.', 'error_type': 'auth_error'}, status=401)
                messages.error(request, "You need to be logged in to perform this action.")
                return redirect(reverse('account_login')) # Adjust to your login URL name

            # Staff/superusers can bypass checks if desired, or you can remove this block
            if request.user.is_staff or request.user.is_superuser:
                logger.info(f"Staff/Superuser {request.user.email} bypassing points check for an action costing {points_cost_arg} points.")
                kwargs['points_required_for_action'] = points_cost_arg
                kwargs['used_free_feature_use'] = False # Staff don't use up free uses by default unless you want them to
                kwargs['will_deduct_ai_points'] = False # Staff don't use up points by default
                return view_func(request, *args, **kwargs)

            try:
                user_profile = request.user.profile
            except AttributeError: # Should not happen if signals are set up correctly
                logger.error(f"UserProfile not found for user {request.user.email} in require_points decorator.")
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'User profile not found. Please contact support.', 'error_type': 'profile_error'}, status=500)
                messages.error(request, "Your user profile could not be loaded. Please contact support.")
                return redirect('document_manager:dashboard') # Or an error page

            kwargs['points_required_for_action'] = points_cost_arg
            kwargs['used_free_feature_use'] = False
            kwargs['will_deduct_ai_points'] = False
            
            # 1. Check for available_free_uses
            if user_profile.available_free_uses > 0:
                # We will consume the free use *inside the view* after the primary action is confirmed successful,
                # but we pass the intent to the view.
                # For now, we just note that a free use is available.
                # The actual deduction of free_use will happen in the view.
                logger.info(f"User {request.user.email} has {user_profile.available_free_uses} free use(s). Action costs {points_cost_arg}. Free use will be prioritized.")
                kwargs['can_use_free_feature_use'] = True # View will decide to use it
                # Proceed to the view, which will handle decrementing free_use if action is successful
                return view_func(request, *args, **kwargs)
            else:
                kwargs['can_use_free_feature_use'] = False


            # 2. If no free uses available, check UserPoints
            try:
                user_points_obj, _ = UserPoints.objects.get_or_create(user=request.user)
                if user_points_obj.balance >= points_cost_arg:
                    logger.info(f"User {request.user.email} has enough AI points ({user_points_obj.balance}) for {points_cost_arg} cost. No free uses were available.")
                    kwargs['will_deduct_ai_points'] = True # View will handle deduction
                    return view_func(request, *args, **kwargs)
                else:
                    logger.warning(f"User {request.user.email} has insufficient AI points ({user_points_obj.balance}) for {points_cost_arg} cost and no free uses.")
                    error_message = (f"You need {points_cost_arg} AI points for this action. "
                                     f"You currently have {user_points_obj.balance} points and no free uses available. "
                                     f"Please purchase more points.")
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({
                            'error': error_message,
                            'error_type': 'insufficient_resources',
                            'current_ai_points_balance': user_points_obj.balance,
                            'current_free_uses': 0,
                            'points_required': points_cost_arg,
                            'prompt_purchase': True
                        }, status=402) # Payment Required
                    messages.error(request, error_message)
                    return redirect('document_manager:purchase_points') # Adjust to your purchase points URL
            except Exception as e: # Catch broader exceptions for UserPoints access
                logger.error(f"Error accessing points balance for {request.user.email}: {e}", exc_info=True)
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Error accessing your points balance.', 'error_type': 'internal_error'}, status=500)
                messages.error(request, "There was an error accessing your points balance.")
                return redirect('document_manager:dashboard') # Adjust

        return _wrapped_view
    return decorator