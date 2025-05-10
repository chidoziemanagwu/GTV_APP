from django.conf import settings

def recaptcha_context(request):
    return {
        'turnstile_site_key': getattr(settings, 'TURNSTILE_SITE_KEY', ''),
        'recaptcha_site_key': getattr(settings, 'RECAPTCHA_PUBLIC_KEY', '')
    }