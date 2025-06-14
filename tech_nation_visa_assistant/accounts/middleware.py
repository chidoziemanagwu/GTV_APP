# accounts/middleware.py

from django.shortcuts import redirect
from django.urls import reverse, NoReverseMatch, Resolver404
from django.contrib import messages
from expert_marketplace.models import Expert # <--- CHANGE THIS: Import Expert model
# from django.contrib.auth.models import Group

class AssessmentRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_url_names = [
            'account_login', 'account_signup', 'account_logout',
            'password_reset', 'password_reset_done',
            'password_reset_confirm', 'password_reset_complete',
            'socialaccount_login', 'socialaccount_signup',
            'home',
            'assessment',
            'terms_privacy',
            'contact',
        ]
        self.exempt_namespaces = [
            'admin',
            'custom_admin',
            'allauth',
            'socialaccount',
            'expert_marketplace', # Good to keep this to exempt the whole expert section
        ]

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated:
            return None

        try:
            resolver_match = request.resolver_match
            current_url_name = resolver_match.url_name if resolver_match else None
            current_namespace = resolver_match.namespace if resolver_match else None
        except Resolver404:
            return None

        if current_url_name in self.exempt_url_names:
            return None
        if current_namespace and current_namespace in self.exempt_namespaces:
            return None

        # --- START OF REFINED EXPERT CHECK ---
        is_expert_user = False
        # Check if the user object has the reverse relation 'expert_profile'
        if hasattr(request.user, 'expert_profile'):
            try:
                # Accessing request.user.expert_profile will get the Expert instance
                # or raise DoesNotExist if it's set but somehow broken (shouldn't happen with OneToOne)
                # or AttributeError if expert_profile is None (meaning no Expert linked)
                expert_instance = request.user.expert_profile
                if expert_instance and expert_instance.is_active: # Check if the linked Expert profile is active
                    is_expert_user = True
            except Expert.DoesNotExist: # Should not be hit if hasattr is true and it's a OneToOne
                is_expert_user = False
            except AttributeError: # This handles the case where request.user.expert_profile is None
                is_expert_user = False
        # --- END OF REFINED EXPERT CHECK ---

        if request.user.is_staff or request.user.is_superuser or is_expert_user:
            return None

        # For regular authenticated users, check if assessment is completed
        profile = getattr(request.user, 'profile', None) # Assuming 'profile' is the related_name for UserProfile

        if profile:
            if not profile.assessment_completed:
                messages.info(request, "Please complete the eligibility assessment first to access this page.")
                try:
                    return redirect(reverse('accounts:assessment'))
                except NoReverseMatch:
                    return None
        else:
            messages.warning(request, "Your profile is not fully set up. Please complete the assessment.")
            try:
                return redirect(reverse('accounts:assessment'))
            except NoReverseMatch:
                return None
            
        return None