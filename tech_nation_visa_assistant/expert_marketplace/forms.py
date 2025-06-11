# expert_marketplace/forms.py
from django import forms
from .models import Booking, Expert
from django.conf import settings
from datetime import datetime, timedelta, time
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.utils.translation import gettext_lazy as _
import json
# from django.forms import BaseModelFormSet # Import BaseModelFormSet
from django.core.exceptions import ValidationError # Import ValidationError
from datetime import datetime


# class BaseAvailabilitySlotFormSet(BaseModelFormSet):
#     def clean(self):
#         super().clean()  # Call parent's clean method first

#         # This clean method is called after individual form cleaning.
#         # We need to check if at least one form is present and not marked for deletion.
#         active_forms_count = 0
#         for form in self.forms:
#             # A form is considered "active" if it has cleaned_data (meaning it was valid and had data)
#             # AND it's not marked for deletion.
#             if hasattr(form, 'cleaned_data') and form.cleaned_data and not form.cleaned_data.get('DELETE', False):
#                 active_forms_count += 1
        
#         if active_forms_count == 0:
#             # This error will be displayed as a non_form_error for the formset.
#             raise ValidationError("You must provide at least one availability slot. Please add a new slot or unmark an existing one for deletion.")







class ConsultationBookingForm(forms.ModelForm):
    # Define time choices - only between 10 AM and 5 PM
    TIME_CHOICES = [
        (time(10, 0).strftime('%H:%M'), '10:00 AM'),
        (time(11, 0).strftime('%H:%M'), '11:00 AM'),
        (time(12, 0).strftime('%H:%M'), '12:00 PM'),
        (time(13, 0).strftime('%H:%M'), '1:00 PM'),
        (time(14, 0).strftime('%H:%M'), '2:00 PM'),
        (time(15, 0).strftime('%H:%M'), '3:00 PM'),
        (time(16, 0).strftime('%H:%M'), '4:00 PM'),
        (time(17, 0).strftime('%H:%M'), '5:00 PM'),
    ]
    
    expertise_needed = forms.ChoiceField(
        choices=Expert.EXPERTISE_CHOICES,
        required=True,
        widget=forms.Select(attrs={
            'class': 'border border-gray-300 text-gray-900 text-sm rounded-lg block w-full p-2.5 ',
            'data-step': '1'
        })
    )
    
    scheduled_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'data-step': '2',
            'min': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        })
    )

    # Replace TimeField with ChoiceField for fixed time slots
    scheduled_time = forms.ChoiceField(
        choices=TIME_CHOICES,
        widget=forms.Select(attrs={
            'class': 'border border-gray-300 text-gray-900 text-sm rounded-lg block w-full p-2.5',
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
    
    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'class': 'block w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 bg-white/90',
            'placeholder': 'Any additional information that might help us match you with the right expert',
            'data-step': '3'
        })
    )

    class Meta:
        model = Booking
        fields = ['expertise_needed', 'name', 'email', 'phone', 'scheduled_date', 
                  'scheduled_time', 'description', 'additional_notes']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user and user.is_authenticated:
            self.fields['name'].initial = f"{user.first_name} {user.last_name}".strip()
            self.fields['email'].initial = user.email
            
            # Make fields readonly if user is logged in
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['email'].widget.attrs['readonly'] = True

    def clean(self):
        cleaned_data = super().clean()
        scheduled_date = cleaned_data.get('scheduled_date')
        
        if scheduled_date:
            from datetime import date
            today = date.today()
            if scheduled_date < today:
                raise forms.ValidationError("Please select a future date for your consultation.")
            
            # Check if date is a weekend
            if scheduled_date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
                raise forms.ValidationError("Consultations are only available on weekdays (Monday to Friday).")

        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.consultation_fee = settings.DEFAULT_CONSULTATION_FEE
        instance.duration_minutes = settings.DEFAULT_CONSULTATION_DURATION
        
        # Convert the time string to a proper time object
        time_str = self.cleaned_data.get('scheduled_time')
        if time_str:
            hour, minute = map(int, time_str.split(':'))
            instance.scheduled_time = time(hour, minute)
        
        if commit:
            instance.save()
        return instance
    

class ExpertProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Expert
        fields = [
            'first_name', 'last_name', 'phone', 
            'expertise', 'specialization', 'bio', 
            'hourly_rate', 'profile_image'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'last_name': forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'phone': forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'expertise': forms.Select(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-500 focus:border-primary-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'specialization': forms.TextInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'bio': forms.Textarea(attrs={'rows': 4, 'class': 'block p-2.5 w-full text-sm text-gray-900 bg-gray-50 rounded-lg border border-gray-300 focus:ring-primary-500 focus:border-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
            'profile_image': forms.ClearableFileInput(attrs={'class': 'block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 dark:text-gray-400 focus:outline-none dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400'}),
        }

    def clean_profile_image(self):
        image = self.cleaned_data.get('profile_image', False)
        if image:
            if image.size > 4*1024*1024: # 4MB limit
                raise forms.ValidationError(_("Image file too large ( > 4MB )"))
            # You can add more image validation if needed (e.g., type, dimensions)
        return image

class ExpertPasswordChangeForm(forms.Form):
    old_password = forms.CharField(
        label=_("Old password"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'autofocus': True, 'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
    )
    new_password1 = forms.CharField(
        label=_("New password"),
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
        strip=False,
        help_text="Your password can’t be too similar to your other personal information. Your password must contain at least 8 characters. Your password can’t be a commonly used password. Your password can’t be entirely numeric." # Add Django's default help text or your own
    )
    new_password2 = forms.CharField(
        label=_("New password confirmation"),
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500'}),
    )

    def __init__(self, expert, *args, **kwargs):
        self.expert = expert
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get("old_password")
        if not self.expert.check_password(old_password):
            raise forms.ValidationError(
                _("Your old password was entered incorrectly. Please enter it again.")
            )
        return old_password

    def clean(self):
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get("new_password1")
        new_password2 = cleaned_data.get("new_password2")
        if new_password1 and new_password2:
            if new_password1 != new_password2:
                self.add_error('new_password2', _("The two password fields didn’t match."))
        # You can add more password validation here, e.g., using Django's password validators
        # from django.contrib.auth.password_validation import validate_password
        # try:
        #     validate_password(new_password1, self.expert.user or self.expert) # Pass user or expert
        # except forms.ValidationError as e:
        #     self.add_error('new_password1', e)
        return cleaned_data

    def save(self, commit=True):
        password = self.cleaned_data["new_password1"]
        self.expert.set_password(password)
        if commit:
            # The Expert model's password field is updated.
            # The associated User model's password (if any) is NOT changed by this form.
            # This is by design for the custom Expert login.
            self.expert.save(update_fields=['password'])
        return self.expert

class ExpertAvailabilityJSONForm(forms.Form):
    """
    This form handles the availability data which will be stored as a JSON string
    in the Expert.availability_json field.
    The 'availability_json_string' field is populated by JavaScript.
    """
    availability_json_string = forms.CharField(widget=forms.HiddenInput(), required=False)

    def clean_availability_json_string(self):
        data_str = self.cleaned_data.get('availability_json_string')
        slots = []

        if not data_str: # If empty string, treat as empty list
            data_str = '[]'
            
        try:
            slots = json.loads(data_str)
            if not isinstance(slots, list):
                raise ValidationError("Availability data must be a list of slots.")
            
            # "At least one availability" rule - you can decide if this is strict.
            # If you allow an empty list to be saved (meaning no availability),
            # you can remove or adjust this check.
            # if not slots: 
            #      raise ValidationError("You must provide at least one availability slot.")

            cleaned_slots = []
            seen_slots = set() # For checking duplicates

            for slot_data in slots:
                if not isinstance(slot_data, dict):
                    raise ValidationError("Each availability slot must be a dictionary.")
                
                date_str = slot_data.get('date')
                start_time_str = slot_data.get('start_time')
                end_time_str = slot_data.get('end_time')

                if not all([date_str, start_time_str, end_time_str]):
                    raise ValidationError("Each slot must have 'date', 'start_time', and 'end_time'.")

                try:
                    # CORRECTED LINE:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    raise ValidationError(f"Invalid date format: '{date_str}'. Use YYYY-MM-DD.")
                
                try:
                    # CORRECTED LINES:
                    start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
                    end_time_obj = datetime.strptime(end_time_str, '%H:%M').time()
                except ValueError:
                    raise ValidationError(f"Invalid time format for date '{date_str}'. Use HH:MM (24-hour).")

                if start_time_obj >= end_time_obj:
                    raise ValidationError(f"Start time ({start_time_str}) must be before end time ({end_time_str}) for date '{date_str}'.")

                # Check for duplicates
                slot_tuple = (date_str, start_time_str, end_time_str) # Make tuple more unique
                if slot_tuple in seen_slots:
                    raise ValidationError(f"Duplicate availability slot found for {date_str} from {start_time_str} to {end_time_str}.")
                seen_slots.add(slot_tuple)
                
                cleaned_slots.append({
                    'date': date_str, 
                    'start_time': start_time_str, 
                    'end_time': end_time_str
                })
            
            # Sort slots by date and then by start_time
            # CORRECTED LINES:
            cleaned_slots.sort(key=lambda s: (datetime.strptime(s['date'], '%Y-%m-%d'), 
                                              datetime.strptime(s['start_time'], '%H:%M')))
            
            return json.dumps(cleaned_slots) # Return the cleaned, validated, sorted JSON string
        
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format for availability data. Please ensure all slots are correctly entered.")
        except ValidationError: # Re-raise our own validation errors
            raise
        except Exception as e: # Catch any other unexpected errors
            # Log this error for debugging
            # Consider using proper logging: import logging; logger = logging.getLogger(__name__); logger.error(...)
            print(f"Unexpected error during availability JSON cleaning: {e}") # This is your log message
            raise ValidationError("An unexpected error occurred while processing availability data. Please check your entries.")


    
class ExpertLoginForm(forms.Form):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'})
    )



# class AvailabilitySlotForm(forms.ModelForm):
#     common_input_classes = "bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white dark:focus:ring-blue-500 dark:focus:border-blue-500"

#     date = forms.DateField(
#         widget=forms.TextInput(attrs={
#             'class': f'{common_input_classes} flatpickr-date', # Target for Flatpickr
#             'placeholder': 'Select date'
#         })
#     )
#     start_time = forms.TimeField(
#         widget=forms.TextInput(attrs={
#             'class': f'{common_input_classes} flatpickr-time', # Target for Flatpickr
#             'placeholder': 'Select start time'
#         })
#     )
#     end_time = forms.TimeField(
#         widget=forms.TextInput(attrs={
#             'class': f'{common_input_classes} flatpickr-time', # Target for Flatpickr
#             'placeholder': 'Select end time'
#         })
#     )

#     class Meta:
#         model = AvailabilitySlot
#         fields = ['date', 'start_time', 'end_time']

#     def clean(self):
#         cleaned_data = super().clean()
#         start_time = cleaned_data.get("start_time")
#         end_time = cleaned_data.get("end_time")
#         date = cleaned_data.get("date")

#         if start_time and end_time and start_time >= end_time:
#             self.add_error('end_time', "End time must be after start time.")
        
#         # Optional: Add validation to prevent past dates/times if needed
#         # if date and date < timezone.now().date():
#         #     self.add_error('date', "Cannot set availability for past dates.")
            
#         return cleaned_data