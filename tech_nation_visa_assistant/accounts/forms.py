# accounts/forms.py

from django import forms
from django.contrib.auth.models import User
from .models import UserProfile
from document_manager.models import Document  # Add this import
from django_countries.fields import CountryField
from django_countries.widgets import CountrySelectWidget
from allauth.account.forms import SignupForm
from referrals.models import ReferralCode, ReferralSignup

TECH_SPECIALIZATION_CHOICES = [
    ('ai_ml', 'Artificial Intelligence / Machine Learning'),
    ('backend', 'Backend Development'),
    ('frontend', 'Frontend Development'),
    ('fullstack', 'Full Stack Development'),
    ('mobile', 'Mobile Development'),
    ('data_science', 'Data Science'),
    ('devops', 'DevOps'),
    ('cloud', 'Cloud Computing'),
    ('cybersecurity', 'Cybersecurity'),
    ('blockchain', 'Blockchain'),
    ('iot', 'Internet of Things'),
    ('game_dev', 'Game Development'),
    ('qa', 'Quality Assurance'),
    ('ui_ux', 'UI/UX Design'),
    ('product_management', 'Product Management'),
    ('other', 'Other')
]

UK_REGION_CHOICES = [
    ('', 'Select a region'),
    ('london', 'London'),
    ('south_east', 'South East'),
    ('south_west', 'South West'),
    ('east_england', 'East of England'),
    ('west_midlands', 'West Midlands'),
    ('east_midlands', 'East Midlands'),
    ('yorkshire', 'Yorkshire and the Humber'),
    ('north_west', 'North West'),
    ('north_east', 'North East'),
    ('wales', 'Wales'),
    ('scotland', 'Scotland'),
    ('northern_ireland', 'Northern Ireland'),
]


class CustomSignupForm(SignupForm):
    referral_code = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter referral code if you have one',
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-primary-500 focus:border-primary-500'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Check if there's a referral code in the request
        request = kwargs.get('request')
        if request and request.GET.get('ref'):
            self.fields['referral_code'].initial = request.GET.get('ref')
            self.fields['referral_code'].widget.attrs['readonly'] = True

    def save(self, request):
        # Save the user first
        user = super().save(request)

        # Process referral code
        referral_code = self.cleaned_data.get('referral_code')
        if referral_code:
            try:
                # Get the referral code object
                ref_code_obj = ReferralCode.objects.get(code=referral_code)

                # Create a referral signup record - removed user_agent field
                ReferralSignup.objects.create(
                    referral_code=ref_code_obj,
                    referred_user=user,
                    ip_address=request.META.get('REMOTE_ADDR', '')
                )

                # Increment the successful_referrals counter instead of signups_count
                ref_code_obj.successful_referrals += 1
                ref_code_obj.save()

            except ReferralCode.DoesNotExist:
                # Invalid referral code, just ignore
                pass

        return user


        
class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()
    
    class Meta:
        model = User
        fields = ['username', 'email']

class ProfileUpdateForm(forms.ModelForm):
    current_country = CountryField(blank_label='Select Country').formfield(
        widget=CountrySelectWidget(attrs={
            'class': 'select2-single form-control',
            'id': 'current_country'
        })
    )
    
    target_uk_region = forms.ChoiceField(
        choices=UK_REGION_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'select2-single form-control',
            'id': 'target_uk_region'
        })
    )
    
    tech_specializations = forms.MultipleChoiceField(
        choices=TECH_SPECIALIZATION_CHOICES,
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'select2-multi form-control',
            'id': 'tech_specializations'
        })
    )

    years_of_experience = forms.IntegerField(
        min_value=0,
        max_value=50,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'years_of_experience'
        })
    )

    github_profile = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'id': 'github_profile',
            'placeholder': 'https://github.com/username'
        })
    )

    linkedin_profile = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'id': 'linkedin_profile',
            'placeholder': 'https://linkedin.com/in/username'
        })
    )

    portfolio_website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'id': 'portfolio_website',
            'placeholder': 'https://yourwebsite.com'
        })
    )

    class Meta:
        model = UserProfile
        fields = [
            'current_country',
            'target_uk_region',
            'tech_specializations',
            'years_of_experience',
            'github_profile',
            'linkedin_profile',
            'portfolio_website'
        ]

    def clean_tech_specializations(self):
        specs = self.cleaned_data.get('tech_specializations', [])
        return list(specs) if specs else []

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'document_type', 'file']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter document title'
            }),
            'document_type': forms.Select(attrs={
                'class': 'form-control'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control'
            })
        }

class AssessmentForm(forms.Form):
    BACKGROUND_CHOICES = [
        ('tech', 'Technical'),
        ('business', 'Business'),
        ('academic', 'Academic'),
    ]

    EXPERIENCE_CHOICES = [
        ('less_than_3', 'Less than 3 years'),
        ('3_to_5', '3-5 years'),
        ('5_to_10', '5-10 years'),
        ('more_than_10', 'More than 10 years'),
    ]

    background_type = forms.ChoiceField(
        choices=BACKGROUND_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500'})
    )

    years_experience = forms.ChoiceField(
        choices=EXPERIENCE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'w-4 h-4 text-primary-600 border-gray-300 focus:ring-primary-500'})
    )

    tech_specializations = forms.MultipleChoiceField(
        choices=TECH_SPECIALIZATION_CHOICES,  # This is defined at the top of your forms.py
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'})
    )

    has_recognition = forms.BooleanField(
        required=False,
        help_text="I have received recognition for my work in the tech industry",
        widget=forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'})
    )

    has_innovation = forms.BooleanField(
        required=False,
        help_text="I have demonstrated innovation in my work",
        widget=forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'})
    )

    has_contribution = forms.BooleanField(
        required=False,
        help_text="I have made significant contributions to the tech community",
        widget=forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500'})
    )




    