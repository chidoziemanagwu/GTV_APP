from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from .models import ReferralCode, ReferralClick, ReferralSignup
import urllib.parse
from django.db.models import Sum

@login_required
def share_link(request):
    """View for sharing referral links"""
    try:
        # Get or create referral code for the user
        referral_code, created = ReferralCode.objects.get_or_create(user=request.user)
        
        # Get base URL (with protocol and domain)
        if request.is_secure():
            protocol = 'https'
        else:
            protocol = 'http'
        domain = request.get_host()
        base_url = f"{protocol}://{domain}"
        
        # Generate share URL
        share_url = f"{base_url}/referrals/join/{referral_code.code}/"
        
        # Generate social media share URLs
        share_text = "Join me on Tech Nation Visa Assistant - the AI-powered platform that helps with your Global Talent visa application!"
        
        # WhatsApp share URL
        whatsapp_share_url = f"https://wa.me/?text={urllib.parse.quote(share_text + ' ' + share_url)}"
        
        # Twitter share URL
        twitter_share_url = f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}&url={urllib.parse.quote(share_url)}"
        
        # Get referral stats
        total_referrals = referral_code.signups.count()
        paying_customers = referral_code.signups.filter(points_awarded=True)
        paying_customers_count = paying_customers.count()
        total_points = paying_customers_count * 3  # 3 points per paying customer
        
        context = {
            'referral_code': referral_code,
            'share_url': share_url,
            'whatsapp_share_url': whatsapp_share_url,
            'twitter_share_url': twitter_share_url,
            'total_referrals': total_referrals,
            'paying_customers_count': paying_customers_count,
            'total_points': total_points,
        }
        
        return render(request, 'referrals/share.html', context)
    
    except Exception as e:
        context = {'error': f"An error occurred: {str(e)}"}
        return render(request, 'referrals/share.html', context)

        

@require_POST
@csrf_protect
@login_required
def track_share(request):
    try:
        referral_code = ReferralCode.objects.get(user=request.user)
        referral_code.shares += 1
        referral_code.save()
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
    referral_code = get_object_or_404(ReferralCode, code=code)

    # Create click record
    ReferralClick.objects.create(
        referral_code=referral_code,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT')
    )

    # Increment click counter
    referral_code.clicks += 1
    referral_code.save()

    return JsonResponse({
        'status': 'success',
        'clicks': referral_code.clicks
    })

def join_with_referral(request, code):
    """Process a referral when someone clicks a referral link"""
    try:
        referral_code = ReferralCode.objects.get(code=code)

        # Track click
        ReferralClick.objects.create(
            referral_code=referral_code,
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )

        # Increment click counter
        referral_code.clicks += 1
        referral_code.save()

        # Check if user is authenticated
        if request.user.is_authenticated:
            messages.success(request, "Referral code applied! Thank you for using a referral link.")
            return redirect('accounts:dashboard')  # Redirect to dashboard if already logged in

        # Redirect to signup with referral code in URL parameter
        return redirect(f'/accounts/signup/?ref={code}')

    except ReferralCode.DoesNotExist:
        # Handle invalid referral code
        messages.error(request, "Invalid referral code.")
        return redirect('home')  # Your home URL

        

@login_required
def referral_stats(request):
    try:
        referral_code = ReferralCode.objects.get(user=request.user)

        # Get recent clicks and signups
        recent_clicks = referral_code.clicks_log.all()[:10]
        recent_signups = referral_code.signups.all()[:10]

        context = {
            'referral_code': referral_code,
            'recent_clicks': recent_clicks,
            'recent_signups': recent_signups,
            'total_clicks': referral_code.clicks,
            'total_shares': referral_code.shares,
            'total_signups': referral_code.signups.count(),
        }

        return render(request, 'referrals/stats.html', context)

    except ReferralCode.DoesNotExist:
        messages.error(request, 'No referral code found.')
        return redirect('referrals:share')