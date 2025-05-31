import requests
from django.conf import settings
from django.core.cache import cache



def verify_recaptcha(request):
    """Verify Google reCAPTCHA token"""
    token = request.POST.get('g-recaptcha-response', '')
    if not token:
        return False

    data = {
        'secret': settings.RECAPTCHA_PRIVATE_KEY,
        'response': token
    }

    try:
        # This is the correct verification URL
        response = requests.post('https://www.google.com/recaptcha/api/siteverify', data=data)
        result = response.json()

        # Check if verification was successful and score is above threshold
        if result.get('success') and result.get('score', 0) >= settings.RECAPTCHA_REQUIRED_SCORE:
            return True
        return False
    except Exception as e:
        print(f"reCAPTCHA verification error: {e}")
        return False
    


def rate_limit_signup(request, max_attempts=3, window_seconds=3600):
    ip = request.META.get('REMOTE_ADDR')
    key = f"signup_attempts_{ip}"
    attempts = cache.get(key, 0)
    if attempts >= max_attempts:
        return False
    cache.set(key, attempts + 1, timeout=window_seconds)
    return True



DISPOSABLE_EMAIL_DOMAINS = {
    'mailinator.com', '10minutemail.com', 'guerrillamail.com', 'tempmail.com', 'yopmail.com', # ...add more
}

def is_disposable_email(email):
    domain = email.split('@')[-1].lower()
    return domain in DISPOSABLE_EMAIL_DOMAINS