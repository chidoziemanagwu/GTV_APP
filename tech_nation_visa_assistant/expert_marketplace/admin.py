# expert_marketplace/admin.py

from django import forms
from django.contrib import admin, messages # Added messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Expert, Booking, Consultation, ExpertEarning, ExpertBonus, NoShowDispute
from django.contrib.auth import get_user_model # For linking User model
import json
import logging # For logging in save_model

logger = logging.getLogger(__name__)
UserModel = get_user_model()

# --- Custom Widgets and Forms ---

class AvailabilityWidget(forms.Textarea):
    """Custom widget for editing expert availability"""
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        attrs['rows'] = 10 # Default rows
        attrs['class'] = f"{attrs.get('class', '')} availability-editor vLargeTextField".strip() # Add Django admin classes
        
        formatted_value = value
        if value and isinstance(value, str):
            try:
                # Try to parse and re-format for pretty printing if it's valid JSON
                parsed_json = json.loads(value)
                formatted_value = json.dumps(parsed_json, indent=2)
            except json.JSONDecodeError:
                pass 
        
        textarea = super().render(name, formatted_value, attrs, renderer)
        
        helper_text = mark_safe("""
        <div class="help" style="margin-bottom: 10px; margin-top: 5px; font-size: 0.9em; color: #555;">
            <p>Enter availability as JSON. Days of the week (lowercase) are keys, and values are lists of time slots (HH:MM-HH:MM).</p>
            <p>Example: <code>{"monday": ["09:00-12:00", "13:00-17:00"], "tuesday": ["10:00-14:00"]}</code></p>
        </div>
        """)
        
        # Correctly escape curly braces for Python's .format() method
        sample_button_html = """
        <button type="button" class="button" id="insert-sample-availability-{name}" 
                onclick="insertSampleAvailabilityForField('{name}')" style="margin-top: 10px; margin-bottom: 5px;">
            Insert Sample Availability
        </button>
        <script>
            if (typeof window.insertSampleAvailabilityForField !== 'function') {{
                window.insertSampleAvailabilityForField = function(fieldName) {{
                    const sampleAvailability = {{ // Escape for Python .format()
                        "monday": ["09:00-12:00", "13:00-17:00"],
                        "tuesday": ["09:00-12:00", "13:00-17:00"],
                        "wednesday": ["09:00-12:00", "13:00-17:00"],
                        "thursday": ["09:00-12:00", "13:00-17:00"],
                        "friday": ["09:00-12:00", "13:00-17:00"],
                        "saturday": [],
                        "sunday": []
                    }}; // Escape for Python .format()
                    const editor = document.querySelector(`textarea[name='${{fieldName}}']`); // Escape fieldName for JS template literal
                    if (editor) {{
                        editor.value = JSON.stringify(sampleAvailability, null, 2);
                    }} else {{
                        console.error(`Editor for field ${{fieldName}} not found.`); // Escape fieldName
                    }}
                }}
            }}
        </script>
        """.format(name=name) 
        
        return mark_safe(helper_text + textarea + sample_button_html)


class ExpertAdminForm(forms.ModelForm):
    class Meta:
        model = Expert
        fields = '__all__'
        widgets = {
            'availability_json': AvailabilityWidget(),
            'bio': forms.Textarea(attrs={'rows': 4}),
        }

# --- ModelAdmins ---

@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    form = ExpertAdminForm
    list_display = ('full_name', 'email', 'expertise', 'tier', 'is_active', 'rating', 'user_linked_status_display')
    list_filter = ('expertise', 'tier', 'is_active', ('user', admin.EmptyFieldListFilter)) 
    search_fields = ('first_name', 'last_name', 'email', 'specialization', 'user__email')
    ordering = ('last_name', 'first_name')
    
    fieldsets = (
        ('User Account Link', {'fields': ('user',)}), 
        ('Personal Information', {'fields': ('first_name', 'last_name', 'email', 'phone', 'profile_image', 'bio')}),
        ('Expertise & Status', {'fields': ('expertise', 'specialization', 'hourly_rate', 'is_active', 'rating')}),
        ('Availability', {'fields': ('availability_json',), 'description': 'Set the expert\'s weekly availability schedule using JSON.'}),
        ('Financial Information', {'fields': ('tier', 'commission_rate', 'total_earnings', 'pending_payout', 'stripe_account_id', 'stripe_details_submitted', 'stripe_payouts_enabled_status')}),
        ('Login & Timestamps', {'fields': ('last_login', 'created_at', 'updated_at'), 'classes': ('collapse',)}),
        ('Statistics', {'fields': ('lifetime_consultations', 'monthly_consultations', 'last_month_reset'), 'classes': ('collapse',)}),
        ('Assignment Data', {'fields': ('last_assigned_at',), 'classes': ('collapse',)}),
    )
    readonly_fields = ('last_login', 'created_at', 'updated_at', 'user_linked_status_display')
    raw_id_fields = ('user',) 

    def user_linked_status_display(self, obj):
        if obj.user:
            user_admin_url = reverse(f"admin:{UserModel._meta.app_label}_{UserModel._meta.model_name}_change", args=[obj.user.pk])
            return format_html('<a href="{}">{} (ID: {})</a> <img src="/static/admin/img/icon-yes.svg" alt="True">', 
                               user_admin_url, obj.user.email, obj.user.pk)
        return format_html('Not Linked <img src="/static/admin/img/icon-no.svg" alt="False">')
    user_linked_status_display.short_description = 'Linked User Account'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if not obj.user and obj.email:
            try:
                user_account, created = UserModel.objects.get_or_create(
                    email__iexact=obj.email,
                    defaults={
                        UserModel.USERNAME_FIELD: obj.email.lower(),
                        'first_name': obj.first_name,
                        'last_name': obj.last_name,
                    }
                )
                if created:
                    user_account.set_unusable_password()
                    user_account.save()
                    logger.info(f"ExpertAdmin: Created and linked new UserModel (ID: {user_account.id}) for Expert {obj.email} (ID: {obj.id}).")
                    messages.success(request, f"Created and linked new User account ({user_account.email}) for Expert {obj.full_name}.")
                else:
                    logger.info(f"ExpertAdmin: Found and linked existing UserModel (ID: {user_account.id}) to Expert {obj.email} (ID: {obj.id}).")
                    messages.info(request, f"Linked existing User account ({user_account.email}) to Expert {obj.full_name}.")

                obj.user = user_account
                obj.save(update_fields=['user']) 

            except UserModel.MultipleObjectsReturned:
                logger.error(f"ExpertAdmin: Multiple UserModels found for email {obj.email} while trying to link Expert {obj.id}. Manual intervention required.")
                messages.error(request, f"Error: Multiple User accounts exist for email {obj.email}. Could not automatically link Expert. Please resolve manually.")
            except Exception as e:
                logger.error(f"ExpertAdmin: Error linking/creating UserModel for Expert {obj.id}: {e}", exc_info=True)
                messages.error(request, f"An unexpected error occurred while trying to link User account for Expert {obj.full_name}: {e}")
        elif obj.user and obj.email and obj.email.lower() != obj.user.email.lower():
            logger.warning(f"ExpertAdmin: Expert {obj.id} email ({obj.email}) differs from linked UserModel email ({obj.user.email}).")
            messages.warning(request, f"Warning: Expert's email ({obj.email}) is different from the linked User account's email ({obj.user.email}). Consider updating the User account email if intended.")


class NoShowDisputeInline(admin.TabularInline):
    model = NoShowDispute
    extra = 0
    fields = ('dispute_type', 'status', 'reason', 'reported_at', 'view_dispute_link')
    readonly_fields = ('reported_at', 'view_dispute_link')
    show_change_link = False 
    verbose_name_plural = 'Associated Disputes'

    def view_dispute_link(self, obj):
        if obj.pk:
            url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
            return format_html('<a href="{}">View/Edit Dispute</a>', url)
        return "N/A (Save booking to create dispute link)"
    view_dispute_link.short_description = 'Dispute Details'


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_or_user_email', 'expert_name_display', 'expertise_needed', 'scheduled_date', 'status', 'created_at')
    list_filter = ('status', 'expertise_needed', 'scheduled_date', 'expert')
    search_fields = ('id', 'name', 'email', 'description', 'expert__first_name', 'expert__last_name', 'expert__email', 'user__email')
    ordering = ('-created_at',)
    autocomplete_fields = ['expert', 'user'] 
    inlines = [NoShowDisputeInline] 
    
    fieldsets = (
        ('Core Details', {'fields': ('status', 'expert', 'user')}),
        ('Client Information (if no linked user or override)', {'fields': ('name', 'email', 'phone')}),
        ('Consultation Details', {'fields': ('expertise_needed', 'scheduled_date', 'scheduled_time', 'duration_minutes', 'description', 'additional_notes', 'meeting_link')}),
        ('Financials', {'fields': ('consultation_fee', 'currency', 'platform_fee', 'expert_earnings', 'refund_amount', 'stripe_payment_intent_id', 'stripe_charge_id', 'stripe_refund_id')}),
        ('Timestamps & Status Info', {'fields': ('created_at', 'updated_at', 'assigned_at', 'completed_at', 'cancelled_at', 'cancellation_reason', 'cancelled_by', 'refund_processed_at'), 'classes': ('collapse',)}),
    )
    readonly_fields = ('created_at', 'updated_at', 'assigned_at', 'completed_at', 'cancelled_at', 'platform_fee', 'expert_earnings', 'refund_processed_at')

    def name_or_user_email(self, obj):
        if obj.user:
            return obj.user.email
        return obj.name or "N/A"
    name_or_user_email.short_description = 'Client (User/Name)'

    def expert_name_display(self, obj):
        if obj.expert:
            return obj.expert.full_name
        return "Unassigned"
    expert_name_display.short_description = 'Expert'


@admin.register(NoShowDispute)
class NoShowDisputeAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking_admin_link', 'dispute_type', 'status', 'client_name_display', 'expert_name_display', 'reported_at')
    list_filter = ('status', 'dispute_type', 'reported_at')
    search_fields = ('booking__id', 'client_name', 'client_email', 'expert_name', 'expert_email', 'reason', 'dispute_code__iexact')
    ordering = ('-reported_at',)
    raw_id_fields = ('booking', 'resolved_by')
    
    fieldsets = (
        ('Dispute Core Information', {
            'fields': ('booking_admin_link', 'dispute_code', 'dispute_type', 'status', 'reason')
        }),
        ('Parties Involved (auto-filled from booking, can be overridden if needed)', {
            'fields': ('client_name', 'client_email', 'expert_name', 'expert_email')
        }),
        ('Expert Response', {
            'fields': ('expert_response', 'expert_response_at', 'expert_evidence_file')
        }),
        ('Resolution Details (Admin)', {
            'fields': ('resolution_notes', 'refund_amount_decided', 'refund_processed_for_dispute', 'resolved_at', 'resolved_by')
        }),
    )
    
    readonly_fields = ('booking_admin_link', 'dispute_code', 'reported_at', 'expert_response_at')

    def booking_admin_link(self, obj):
        if obj.booking:
            url = reverse(f"admin:{Booking._meta.app_label}_{Booking._meta.model_name}_change", args=[obj.booking.id])
            return format_html('<a href="{}">Booking #{}</a>', url, obj.booking.id)
        return "No associated booking"
    booking_admin_link.short_description = 'Booking'

    def client_name_display(self, obj):
        return obj.client_name or (obj.booking.user.get_full_name() if obj.booking and obj.booking.user else obj.booking.email if obj.booking else "N/A")
    client_name_display.short_description = 'Client'

    def expert_name_display(self, obj):
        return obj.expert_name or (obj.booking.expert.full_name if obj.booking and obj.booking.expert else "N/A")
    expert_name_display.short_description = 'Expert'


@admin.register(Consultation) 
class ConsultationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 
        'booking_link_display', 
        'user_email_display', 
        'expert_name_display', 
        'scheduled_start_time', 
        'duration_minutes',     
        'consultation_type',    
        'client_rating_for_expert', 
        'status'
    ]
    list_filter = [
        'consultation_type',    
        'status', 
        'scheduled_start_time',
        'expert',
        'user'
    ]
    search_fields = ['booking__id', 'user__email', 'expert__email', 'expert__first_name', 'expert__last_name']
    ordering = ['-scheduled_start_time'] 
    raw_id_fields = ('booking', 'user', 'expert')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ("Core Info", {"fields": ("booking", "user", "expert", "status", "consultation_type")}),
        ("Timing", {"fields": ("scheduled_start_time", "duration_minutes", "actual_start_time", "actual_end_time", "actual_duration_minutes")}),
        ("Feedback & Notes", {"fields": ("notes_by_expert", "notes_by_client", "client_rating_for_expert", "client_review_for_expert", "expert_rating_for_client", "expert_feedback_on_client")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)})
    )

    def booking_link_display(self, obj):
        if obj.booking:
            url = reverse(f"admin:{Booking._meta.app_label}_{Booking._meta.model_name}_change", args=[obj.booking.id])
            return format_html('<a href="{}">Booking #{}</a>', url, obj.booking.id)
        return "N/A"
    booking_link_display.short_description = "Booking"

    def user_email_display(self, obj):
        return obj.user.email if obj.user else "N/A"
    user_email_display.short_description = "Client Email"

    def expert_name_display(self, obj):
        return obj.expert.full_name if obj.expert else "N/A"
    expert_name_display.short_description = "Expert"


@admin.register(ExpertEarning)
class ExpertEarningAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'expert_link', 
        'booking_link', 
        'amount', 
        'currency', 
        'platform_fee_recorded',
        'status', 
        'calculated_at',
        'paid_at',
        'transaction_id'
    )
    list_filter = (
        'status', 
        'currency',
        'expert',
        'calculated_at',
        'paid_at'
    )
    search_fields = ('expert__first_name', 'expert__last_name', 'expert__email', 'booking__id', 'transaction_id')
    ordering = ('-calculated_at',)    
    raw_id_fields = ('expert', 'booking') 
    readonly_fields = ('calculated_at', 'paid_at')

    def expert_link(self, obj):
        if obj.expert:
            url = reverse(f"admin:{Expert._meta.app_label}_{Expert._meta.model_name}_change", args=[obj.expert.id])
            return format_html('<a href="{}">{}</a>', url, obj.expert.full_name)
        return "N/A"
    expert_link.short_description = "Expert"

    def booking_link(self, obj):
        if obj.booking:
            url = reverse(f"admin:{Booking._meta.app_label}_{Booking._meta.model_name}_change", args=[obj.booking.id])
            return format_html('<a href="{}">Booking #{}</a>', url, obj.booking.id)
        return "N/A (Manual Earning/Bonus)"
    booking_link.short_description = "Booking"


@admin.register(ExpertBonus)
class ExpertBonusAdmin(admin.ModelAdmin):
    list_display = ('id', 'expert_link', 'amount', 'currency', 'reason', 'status', 'created_at', 'paid_at', 'transaction_id')
    list_filter = ('status', 'currency', 'expert', 'created_at', 'paid_at')
    search_fields = ('expert__first_name', 'expert__last_name', 'expert__email', 'reason', 'description', 'transaction_id')
    ordering = ('-created_at',)
    raw_id_fields = ('expert',)
    readonly_fields = ('created_at', 'paid_at')

    def expert_link(self, obj):
        if obj.expert:
            url = reverse(f"admin:{Expert._meta.app_label}_{Expert._meta.model_name}_change", args=[obj.expert.id])
            return format_html('<a href="{}">{}</a>', url, obj.expert.full_name)
        return "N/A"
    expert_link.short_description = "Expert"