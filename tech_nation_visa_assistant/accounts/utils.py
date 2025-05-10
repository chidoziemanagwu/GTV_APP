import requests
from django.conf import settings

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