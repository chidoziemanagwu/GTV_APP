# expert_marketplace/forms.py
from django import forms
from .models import Booking

class ConsultationBookingForm(forms.ModelForm):
    scheduled_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'data-step': '2'
        })
    )

    scheduled_time = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'data-step': '2'
        })
    )

    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'placeholder': 'Your full name',
            'data-step': '3'
        })
    )

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'placeholder': 'Your email address',
            'data-step': '3'
        })
    )

    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'placeholder': 'Your phone number',
            'data-step': '3'
        })
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'placeholder': 'Please describe your situation and what you need help with',
            'data-step': '3'
        })
    )

    class Meta:
        model = Booking
        fields = ['name', 'email', 'phone', 'scheduled_date', 'scheduled_time', 'description']

    def clean(self):
        cleaned_data = super().clean()
        scheduled_date = cleaned_data.get('scheduled_date')
        scheduled_time = cleaned_data.get('scheduled_time')

        if scheduled_date and scheduled_time:
            # Add any validation logic here if needed
            # For example, checking if the date is not in the past
            from datetime import datetime, date
            today = date.today()
            if scheduled_date < today:
                raise forms.ValidationError("Please select a future date for your consultation.")

        return cleaned_data