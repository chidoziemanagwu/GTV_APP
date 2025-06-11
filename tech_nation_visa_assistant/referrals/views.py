# referrals/views.py (optimized)

from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from .models import ReferralCode, ReferralClick, ReferralSignup
import urllib.parse
from django.db.models import Sum
from django.utils import timezone
import logging
from accounts.utils import verify_recaptcha, is_disposable_email, rate_limit_signup

logger = logging.getLogger(__name__)

@login_required
def share_link(request):
    """View for sharing referral links - optimized with caching"""
    try:
        referral_code, created = ReferralCode.objects.get_or_create(user=request.user)

        if request.is_secure():
            protocol = 'https'
        else:
            protocol = 'http'
        domain = request.get_host()
        base_url = f"{protocol}://{domain}"
        share_url = f"{base_url}/referrals/join/{referral_code.code}/"
        share_text = "Join me on Tech Nation Visa Assistant - the AI-powered platform that helps with your Global Talent visa application!"
        whatsapp_share_url = f"https://wa.me/?text={urllib.parse.quote(share_text + ' ' + share_url)}"
        twitter_share_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}&url={urllib.parse.quote(share_url)}"

        # Get referral stats
        # Total signups made using this user's referral code
        total_signups_via_this_code = referral_code.signups.count()

        # Count of signups that resulted in a free use being granted to the referrer
        successful_referrals_for_this_code = referral_code.signups.filter(free_use_granted=True).count()
        
        # Referrer's current total available free uses (from their profile)
        # This is accessed directly in the template via request.user.profile.available_free_uses

        logger.info(f"User: {request.user.username}, Total Signups via code: {total_signups_via_this_code}, Successful Referrals (earned free use): {successful_referrals_for_this_code}, Current Available Free Uses: {request.user.profile.available_free_uses}")

        context = {
            'referral_code': referral_code,
            'share_url': share_url,
            'whatsapp_share_url': whatsapp_share_url,
            'twitter_share_url': twitter_share_url,
            'total_referrals_count': total_signups_via_this_code, # For the card: "Total Referrals"
            'successful_referrals_count': successful_referrals_for_this_code, # For the card: "Successful Referrals"
            # 'referrer_available_free_uses' is accessed via request.user.profile.available_free_uses in template
            'referrals': referral_code.signups.select_related('referred_user', 'referred_user__profile').order_by('-timestamp'),
        }
        return render(request, 'referrals/share.html', context)
    except Exception as e:
        logger.error(f"Error in share_link: {e}", exc_info=True) # Added exc_info for more details
        context = {'error': f"An error occurred: {str(e)}"}
        return render(request, 'referrals/share.html', context)


    
        
    

@require_POST
@csrf_protect
@login_required
def track_share(request):
    """Track when a user shares their referral link"""
    try:
        referral_code = ReferralCode.objects.get(user=request.user)
        referral_code.shares += 1
        referral_code.save(update_fields=['shares'])  # Only update the shares field
        
        # Clear cache for share_link view
        cache_key = f"views.decorators.cache.cache_page.{request.get_host()}.GET.{request.user.id}"
        cache.delete(cache_key)
        
        return JsonResponse({
            'status': 'success',
            'shares': referral_code.shares
        })
    except ReferralCode.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Referral code not found'
        }, status=404)

def track_click(request, code):
    """Track clicks on referral links"""
    try:
        referral_code = get_object_or_404(ReferralCode, code=code)

        # Create click record
        ReferralClick.objects.create(
            referral_code=referral_code,
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        # Increment click counter - use F() expression to avoid race conditions
        from django.db.models import F
        ReferralCode.objects.filter(code=code).update(clicks=F('clicks') + 1)

        # Get updated click count
        referral_code.refresh_from_db()
        
        return JsonResponse({
            'status': 'success',
            'clicks': referral_code.clicks
        })
    except Exception as e:
        logger.error(f"Error tracking click: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)



def join_with_referral(request, code):
    """Process a referral when someone clicks a referral link, with anti-gaming."""
    try:
        referral_code = ReferralCode.objects.get(code=code)
        ip = request.META.get('REMOTE_ADDR', '')

        # Track click
        ReferralClick.objects.create(
            referral_code=referral_code,
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        from django.db.models import F
        ReferralCode.objects.filter(code=code).update(clicks=F('clicks') + 1)

        # If user is authenticated, prevent self-referral
        if request.user.is_authenticated:
            if request.user == referral_code.user:
                messages.error(request, "You cannot refer yourself.")
                return redirect('accounts:dashboard')
            messages.success(request, "Referral code applied! Thank you for using a referral link.")
            return redirect('accounts:dashboard')

        # --- Anti-gaming: Limit referrals per IP per day ---
        recent_referrals = ReferralSignup.objects.filter(
            ip_address=ip,
            timestamp__gte=timezone.now() - timedelta(days=1)
        ).count()
        if recent_referrals >= 3:
            messages.error(request, "Too many referrals from this IP address. Please try again later.")
            return redirect('account_signup')

        # --- Store referral code in session for use after signup ---
        request.session['referral_code'] = code

        # Redirect to signup with referral code in URL parameter
        return redirect(f'/accounts/signup/?ref={code}')

    except ReferralCode.DoesNotExist:
        messages.error(request, "Invalid referral code.")
        return redirect('home')
    except Exception as e:
        logger.error(f"Error in join_with_referral: {e}")
        messages.error(request, "An error occurred while processing your referral.")
        return redirect('home')



@login_required
def referral_stats(request):
    """View referral statistics"""
    try:
        # Get referral code with prefetch
        referral_code = get_object_or_404(ReferralCode, user=request.user)

        # Get referral stats with efficient queries
        total_clicks = referral_code.clicks
        total_signups = referral_code.signups.count()
        conversion_rate = (total_signups / total_clicks * 100) if total_clicks > 0 else 0

        # Get paying customers with a single query
        paying_customers = referral_code.signups.filter(points_awarded=True)
        paying_customers_count = paying_customers.count()

        # Calculate points (3 per paying customer)
        total_points = paying_customers_count * 3

        # Get recent signups with select_related for efficiency
        recent_signups = referral_code.signups.select_related('referred_user').order_by('-created_at')[:5]

        context = {
            'referral_code': referral_code,
            'total_clicks': total_clicks,
            'total_signups': total_signups,
            'conversion_rate': round(conversion_rate, 2),
            'paying_customers_count': paying_customers_count,
            'total_points': total_points,
            'recent_signups': recent_signups,
        }

        return render(request, 'referrals/stats.html', context)

    except Exception as e:
        logger.error(f"Error in referral_stats: {e}")
        messages.error(request, f"An error occurred: {str(e)}")
        return redirect('referrals:share_link')

@login_required
def redeem_points(request):
    """Redeem referral points for rewards"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    try:
        # Get referral code
        referral_code = get_object_or_404(ReferralCode, user=request.user)

        # Calculate available points
        paying_customers = referral_code.signups.filter(points_awarded=True).count()
        available_points = paying_customers * 3

        # Get points already redeemed
        redeemed_points = referral_code.redeemed_points

        # Calculate remaining points
        remaining_points = available_points - redeemed_points

        # Get reward ID and points required
        reward_id = request.POST.get('reward_id')
        points_required = int(request.POST.get('points_required', 0))

        # Check if user has enough points
        if remaining_points < points_required:
            return JsonResponse({
                'status': 'error',
                'message': f'Not enough points. You have {remaining_points} points, but {points_required} are required.'
            })

        # Process redemption - in a real app, you'd create a redemption record
        referral_code.redeemed_points += points_required
        referral_code.save(update_fields=['redeemed_points'])  # Only update this field

        # Return success response
        return JsonResponse({
            'status': 'success',
            'message': 'Points redeemed successfully!',
            'remaining_points': remaining_points - points_required
        })

    except Exception as e:
        logger.error(f"Error in redeem_points: {e}")
        return JsonResponse({
            'status': 'error',
            'message': f'An error occurred: {str(e)}'
        }, status=500)