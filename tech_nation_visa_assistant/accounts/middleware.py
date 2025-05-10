# accounts/middleware.py

from django.shortcuts import redirect
from django.urls import resolve, reverse
from django.contrib import messages

class AssessmentRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_url = resolve(request.path_info).url_name
            exempt_urls = [
                'assessment',
                'logout',
                'password_change',
                'password_reset',
                'account_logout',
                'account_reset_password',
            ]

            if current_url not in exempt_urls:
                profile = getattr(request.user, 'profile', None)
                if profile and not profile.assessment_completed:
                    messages.info(request, "Please complete the eligibility assessment first.")
                    return redirect('accounts:assessment')

        response = self.get_response(request)
        return response