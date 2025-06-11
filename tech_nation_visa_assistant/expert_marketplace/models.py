# expert_marketplace/models.py
from django.db import models
from django.conf import settings # For settings.DEFAULT_CURRENCY
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import json
from django.contrib.auth import get_user_model
import uuid
from decimal import Decimal
from django.contrib.auth.hashers import make_password, check_password # Added for password handling
import datetime # Added for Consultation model save method
import stripe 


User = get_user_model() # This is your accounts.User model


def get_default_currency():
    # Ensure DEFAULT_CURRENCY is set in your settings.py
    # and that it's a string that can have .upper() called on it.
    if hasattr(settings, 'DEFAULT_CURRENCY') and settings.DEFAULT_CURRENCY:
        return settings.DEFAULT_CURRENCY.upper()
    return "GBP" # Fallback if not set, or adjust as needed


class Expert(models.Model):
    EXPERTISE_CHOICES = [
        ('tech', 'Tech'),
        ('business', 'Business'),
        ('academic', 'Academic'),
        ('arts', 'Arts'),
    ]
    
    TIER_CHOICES = [
        ('bronze', 'Bronze'), # Base tier
        ('silver', 'Silver'),
        ('gold', 'Gold'),
        ('platinum', 'Platinum'), # Top tier
    ]

    # This field will be linked by the custom auth backend on first successful login
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, # If the linked User is deleted, delete the Expert profile
        related_name='expert_profile', 
        null=True, 
        blank=True
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(
        unique=True, 
        help_text="Expert's primary email, used for login."
    ) # This email will be used for login
    
    # --- NEW: Password field for Expert login ---
    password = models.CharField(
        max_length=128, 
        help_text="Hashed password for expert login. Use 'set_password' to set it."
    )
    # --- END NEW ---

    phone = models.CharField(max_length=20, blank=True, null=True)
    expertise = models.CharField(max_length=20, choices=EXPERTISE_CHOICES)
    specialization = models.CharField(max_length=100, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    profile_image = models.ImageField(upload_to='experts/', blank=True, null=True)
    is_active = models.BooleanField(
        default=True, 
        help_text="Designates whether this expert can log in and is considered active."
    ) # Crucial for login
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    
    last_assigned_at = models.DateTimeField(null=True, blank=True)
    availability_json = models.TextField(default='[]', blank=True)
    
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='bronze')
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=Decimal('0.40') 
    )
    total_earnings = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    pending_payout = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    lifetime_consultations = models.PositiveIntegerField(default=0)
    monthly_consultations = models.PositiveIntegerField(default=0)
    last_month_reset = models.DateField(null=True, blank=True)
    total_earnings_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00')) # Total actually sent

    stripe_account_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Stripe Connected Account ID for payouts (e.g., acct_xxxxxxxxxxxxxx)"
    )
    
    stripe_details_submitted = models.BooleanField(
        default=False,
        help_text="Reflects if the expert has submitted all required details to Stripe."
    )
    stripe_charges_enabled = models.BooleanField(
        default=False,
        help_text="Reflects if charges are enabled for the Stripe account (less critical for payouts)."
    )
    stripe_payouts_enabled_status = models.BooleanField(
        default=False,
        help_text="Reflects if payouts are enabled for the Stripe account. True if payouts_enabled."
    )
    
    # --- NEW: For tracking login, similar to User model ---
    last_login = models.DateTimeField(blank=True, null=True)
    # --- END NEW ---
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    # --- NEW: Password management methods ---
    def set_password(self, raw_password):
        self.password = make_password(raw_password)
        # self._password = raw_password # Optionally store raw password temporarily if needed before save

    def check_password(self, raw_password):
        """
        Return a boolean of whether the raw_password was correct. Handles
        hashing formats behind the scenes.
        """
        # The 'setter' argument to check_password is for password hash upgrades.
        # Since this is a new field, we don't strictly need to handle upgrades here,
        # but it's good practice if you were migrating existing unhashed passwords.
        # For new passwords, it won't be called if the hash is current.
        def setter(new_raw_password):
            self.set_password(new_raw_password)
            # self.save(update_fields=["password"]) # Be careful with save() in methods called by other save()
                                                  # or during authentication.
                                                  # The custom backend will handle saving last_login.
        return check_password(raw_password, self.password, setter)
    # --- END NEW ---

    @property
    def is_authenticated(self):
        """
        Always True for an instance of an Expert that might represent a logged-in user.
        This is more for compatibility if the Expert model itself is treated like a user object
        in some contexts, though our backend will return an accounts.User instance.
        """
        return True

    def get_availability(self):
        try:
            return json.loads(self.availability_json)
        except (json.JSONDecodeError, TypeError): 
            return {}
    
    def set_availability(self, availability_dict):
        self.availability_json = json.dumps(availability_dict)
        
    def update_monthly_stats(self):
        today = timezone.now().date()
        if not self.last_month_reset or (today.month != self.last_month_reset.month or 
                                         today.year != self.last_month_reset.year):
            self.monthly_consultations = 0
            self.last_month_reset = today
            # self.save() # Avoid save() here if this method is called within another save operation.
                         # Pass update_fields if necessary.

    def update_tier(self):
        """Updates expert's tier and platform commission rate based on performance."""
        new_tier = 'bronze'
        new_commission_rate = Decimal('0.40') 

        if self.lifetime_consultations >= 100 and self.rating >= Decimal('4.5'):
            new_tier = 'platinum'
            new_commission_rate = Decimal('0.25')
        elif self.lifetime_consultations >= 50 and self.rating >= Decimal('4.0'):
            new_tier = 'gold'
            new_commission_rate = Decimal('0.30')
        elif self.lifetime_consultations >= 20 and self.rating >= Decimal('3.5'):
            new_tier = 'silver'
            new_commission_rate = Decimal('0.35')
        
        changed = False
        if self.tier != new_tier:
            self.tier = new_tier
            changed = True
        if self.commission_rate != new_commission_rate:
            self.commission_rate = new_commission_rate
            changed = True
        
        if changed and self.pk: # Ensure self.pk exists before trying to save with update_fields
            self.save(update_fields=['tier', 'commission_rate'])
        elif changed: # For new objects, a full save is fine
            pass # The main save() call will handle it

    def stripe_payouts_enabled(self): # Example method
        if not self.stripe_account_id:
            return False
        try:
            account = stripe.Account.retrieve(self.stripe_account_id)
            return account.payouts_enabled
        except Exception:
            return False
    def __str__(self):
        return self.full_name
    

class Booking(models.Model):
    # ... your existing fields like expert, user, scheduled_date, scheduled_time ...
    STATUS_CHOICES = [
        ('pending_payment', 'Pending Payment'),
        ('awaiting_assignment', 'Awaiting Expert Assignment'),
        ('confirmed', 'Confirmed'), 
        ('completed', 'Completed'), 
        ('cancelled', 'Cancelled'), 
        ('refunded', 'Refunded'), 
        ('partially_refunded', 'Partially Refunded'),
        ('expert_noshow', 'Expert No-Show'),
        ('client_noshow', 'Client No-Show'),
        ('dispute', 'Dispute'),
    ]

    expert = models.ForeignKey(Expert, on_delete=models.SET_NULL, related_name='bookings', null=True, blank=True) 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='expert_bookings', null=True, blank=True) 
    
    name = models.CharField(max_length=100, default='') 
    email = models.EmailField(default='') 
    phone = models.CharField(max_length=20, default='', blank=True) 
    description = models.TextField(default='', help_text="Brief description of what the user needs help with.")
    
    scheduled_date = models.DateField(null=True, blank=True)
    scheduled_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=30, validators=[MinValueValidator(15)]) 
    
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    currency = models.CharField(max_length=3, default=get_default_currency)

    expertise_needed = models.CharField(max_length=20, choices=Expert.EXPERTISE_CHOICES, null=True, blank=True)
    additional_notes = models.TextField(blank=True, null=True, help_text="Any other details for the expert or admin.")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_payment')
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True, null=True) 
    
    stripe_refund_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stores the ID of the latest Stripe refund object.")
    refund_processed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when the last refund was processed via Stripe.")

    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expert_earnings = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    expert_response_deadline = models.DateTimeField(null=True, blank=True) 
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    assigned_at = models.DateTimeField(null=True, blank=True) 
    completed_at = models.DateTimeField(null=True, blank=True) 
    completion_notes = models.TextField(blank=True, null=True) 
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True, null=True)
    
    cancelled_by = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        help_text="Indicates who initiated the cancellation (e.g., 'client', 'expert', 'system', 'admin')"
    )

    meeting_link = models.URLField(blank=True, null=True)
    reschedule_count = models.PositiveIntegerField(default=0)

    # ... other fields ...

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        expert_name = self.expert.full_name if self.expert else 'Unassigned'
        user_name_display = self.name or (self.user.get_full_name() if self.user and hasattr(self.user, 'get_full_name') and callable(self.user.get_full_name) and self.user.get_full_name() else self.email or 'Unknown User')
        return f"Booking for {user_name_display} with {expert_name} on {self.scheduled_date or 'N/A'}"
        
    def _calculate_and_set_financials(self):
        if self.expert and self.consultation_fee is not None and self.expert.commission_rate is not None:
            platform_commission_decimal = Decimal(str(self.expert.commission_rate))
            self.platform_fee = (self.consultation_fee * platform_commission_decimal).quantize(Decimal('0.01'))
            self.expert_earnings = (self.consultation_fee - self.platform_fee).quantize(Decimal('0.01'))
        else:
            self.platform_fee = None
            self.expert_earnings = None

    def save(self, *args, **kwargs):
        if not self.currency and hasattr(settings, 'DEFAULT_CURRENCY'):
            self.currency = settings.DEFAULT_CURRENCY.upper()
        # Calculate financials before every save, but only if relevant fields are present
        if self.expert and self.consultation_fee is not None and self.expert.commission_rate is not None:
            self._calculate_and_set_financials()
        super().save(*args, **kwargs) # Call the "real" save() method.

    def calculate_financials(self, and_save=False):
        self._calculate_and_set_financials()
        if and_save:
            if self.pk:
                self.save(update_fields=['platform_fee', 'expert_earnings', 'currency'])
            else:
                self.save()

    # --- ADD THIS METHOD ---
    def get_scheduled_datetime_aware(self):
        """
        Combines scheduled_date and scheduled_time into a timezone-aware datetime object.
        Returns None if date or time is not set.
        """
        if self.scheduled_date and self.scheduled_time:
            naive_dt = datetime.datetime.combine(self.scheduled_date, self.scheduled_time)
            # Assuming settings.TIME_ZONE is your project's default timezone
            # and timezone is imported from django.utils
            return timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
        return None

class Consultation(models.Model):
    TYPE_CHOICES = [
        ('video', 'Video Call'),
        ('audio', 'Audio Call'),
        ('chat', 'Chat'),
    ]

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='consultation_record')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_consultations')
    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='expert_consultations')
    
    scheduled_start_time = models.DateTimeField(null=True, blank=True) 
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    
    duration_minutes = models.IntegerField(help_text="Planned duration in minutes", null=True, blank=True)
    actual_duration_minutes = models.IntegerField(help_text="Actual duration in minutes", null=True, blank=True)

    consultation_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='video')
    notes_by_expert = models.TextField(blank=True, null=True)
    notes_by_client = models.TextField(blank=True, null=True)
    
    client_rating_for_expert = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], blank=True, null=True)
    client_review_for_expert = models.TextField(blank=True, null=True)
    
    expert_rating_for_client = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], blank=True, null=True)
    expert_feedback_on_client = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=20, default='scheduled', choices=[
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show_client', 'Client No-Show'),
        ('no_show_expert', 'Expert No-Show'),
    ])
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.booking: 
            if not self.user_id and self.booking.user_id: self.user_id = self.booking.user_id
            if not self.expert_id and self.booking.expert_id: self.expert_id = self.booking.expert_id
            if not self.scheduled_start_time and self.booking.scheduled_date and self.booking.scheduled_time:
                # Combine date and time into a datetime object
                combined_dt = datetime.datetime.combine(self.booking.scheduled_date, self.booking.scheduled_time)
                # Make it timezone-aware if it's naive, using the current default timezone
                if timezone.is_naive(combined_dt):
                    self.scheduled_start_time = timezone.make_aware(combined_dt)
                else:
                    self.scheduled_start_time = combined_dt

            if not self.duration_minutes: self.duration_minutes = self.booking.duration_minutes
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Consultation for Booking {self.booking_id} with {self.expert.full_name if self.expert else 'N/A'}"


class ExpertEarning(models.Model):
    PENDING = 'pending'
    PAID = 'paid'
    FAILED = 'failed' 
    CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (PENDING, 'Pending Payout'),
        (PAID, 'Paid Out'),
        (FAILED, 'Payout Failed'),
        (CANCELLED, 'Cancelled'),
    ]

    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='all_earnings_records')
    booking = models.OneToOneField(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='expert_earning_record')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2) 
    currency = models.CharField(max_length=3, default=get_default_currency)
    platform_fee_recorded = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    calculated_at = models.DateTimeField(auto_now_add=True, help_text="When this earning was calculated and recorded.")
    paid_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when payout was successfully processed.")
    
    payment_method = models.CharField(max_length=50, blank=True, null=True, help_text="Method used for payout (e.g., stripe_transfer, paypal)")
    transaction_id = models.CharField(max_length=255, blank=True, null=True, help_text="Stripe Transfer ID or other payment processor transaction ID")
    notes = models.TextField(blank=True, null=True, help_text="Internal notes, e.g., error messages for failed payouts, reasons for cancellation.")

    def __str__(self):
        expert_name = self.expert.full_name if self.expert else "Unknown Expert"
        booking_id_str = f"Booking {self.booking.id}" if self.booking else "No Associated Booking"
        return f"Earning for {expert_name} from {booking_id_str} - {self.amount} {self.currency} ({self.get_status_display()})"

class ExpertBonus(models.Model):
    PENDING = 'pending'
    PAID = 'paid'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (PENDING, 'Pending Payout'),
        (PAID, 'Paid Out'),
        (FAILED, 'Payout Failed'),
        (CANCELLED, 'Cancelled'),
    ]

    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='bonuses')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default=get_default_currency)
    reason = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    transaction_id = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Bonus of {self.amount} {self.currency} for {self.expert.full_name}: {self.reason} ({self.get_status_display()})"
    

class NoShowDispute(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('expert_responded', 'Expert Responded'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('rejected', 'Rejected'),
    )
    
    DISPUTE_TYPE_CHOICES = (
        ('expert_noshow', 'Expert No-Show (Reported by Client)'), # Clarified
        ('client_noshow', 'Client No-Show (Reported by Expert)'), # Added
        ('quality', 'Quality Issue'),
        ('technical', 'Technical Issue'),
        ('other', 'Other'),
    )
    
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='disputes')
    dispute_type = models.CharField(max_length=20, choices=DISPUTE_TYPE_CHOICES, default='other')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    client_name = models.CharField(max_length=255, blank=True) 
    client_email = models.EmailField(blank=True) 
    
    expert_name = models.CharField(max_length=255, blank=True) 
    expert_email = models.EmailField(blank=True) 
    
    reported_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    expert_response = models.TextField(blank=True, null=True)
    expert_response_at = models.DateTimeField(null=True, blank=True)
    expert_evidence_file = models.FileField(upload_to='dispute_evidence/', null=True, blank=True)
    
    resolution_notes = models.TextField(blank=True, null=True)
    refund_amount_decided = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    refund_processed_for_dispute = models.BooleanField(default=False) 
    
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='resolved_disputes_by_admin',
        help_text="Admin user who resolved the dispute."
    )

    dispute_code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    def __str__(self):
        return f"Dispute for Booking ID {self.booking_id} - Status: {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        if self.booking:
            if not self.client_name and self.booking.name:
                self.client_name = self.booking.name
            if not self.client_email and self.booking.email:
                self.client_email = self.booking.email
            if self.booking.expert:
                if not self.expert_name:
                    self.expert_name = self.booking.expert.full_name
                if not self.expert_email:
                    self.expert_email = self.booking.expert.email
        
        super().save(*args, **kwargs)



