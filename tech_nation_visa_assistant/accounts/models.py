# accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_countries.fields import CountryField
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
import logging # Import logging
from django.db import IntegrityError


# It's good practice to import models from other apps at the top if they are frequently used
# or within methods/signals if they cause circular import issues (less likely here).
# from referrals.models import ReferralCode # For create_referral_code method

logger = logging.getLogger(__name__) # Initialize logger

class User(AbstractUser):
    ACCOUNT_TYPE_CHOICES = (
        ('free', 'Free'),
        ('pay_once', 'Pay Once'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    )

    STAGE_CHOICES = (
        ('assessment', 'Initial Assessment'),
        ('preparation', 'Document Preparation'),
        ('review', 'Application Review'),
        ('submission', 'Submission Stage'),
        ('post_submission', 'Post Submission'),
    )

    PATH_CHOICES = (
        ('talent', 'Exceptional Talent'),
        ('promise', 'Exceptional Promise'),
        ('undecided', 'Undecided'),
    )

    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default='free')
    application_stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='assessment')
    visa_path = models.CharField(max_length=20, choices=PATH_CHOICES, default='undecided')

    is_technical = models.BooleanField(default=False)
    is_business = models.BooleanField(default=False)
    years_experience = models.IntegerField(default=0)

    subscription_active = models.BooleanField(default=False)
    subscription_end_date = models.DateTimeField(null=True, blank=True)

    notify_guide_changes = models.BooleanField(default=True)
    notify_app_updates = models.BooleanField(default=True)

    has_recognition = models.BooleanField(default=False)
    has_innovation = models.BooleanField(default=False)
    has_contribution = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    def __str__(self):
        return self.email

    def award_referral_points(self):
        """Award points to referrer when user becomes a paying customer"""
        # This method seems to be designed to be called when a user makes a payment.
        # It assumes 'self' is the referred user.
        # The logic for awarding points is now primarily in ReferralSignup.award_rewards()
        # This method might need to be re-evaluated or simplified if ReferralSignup.award_rewards()
        # is the primary mechanism.
        # For now, let's assume it's called correctly.
        try:
            # 'referred_signups' should be the related_name from ReferralSignup.referred_user
            # If ReferralSignup.referred_user is OneToOneField(User, related_name='referral_signup_info')
            # then you'd use self.referral_signup_info
            # Let's assume the related_name on ReferralSignup.referred_user is 'referred_signup_record'
            # For example: referred_user = models.OneToOneField(User, ..., related_name='referred_signup_record')
            
            # Check if this user was referred
            if hasattr(self, 'referral_signup_info'): # Assuming related_name='referral_signup_info'
                referral_signup = self.referral_signup_info
                if not referral_signup.has_been_rewarded: # Use the flag from ReferralSignup
                    # Call the central reward awarding method on ReferralSignup
                    if referral_signup.award_rewards(): # This now handles points and free uses
                        logger.info(f"Successfully awarded referral rewards via User.award_referral_points for {self.email} to {referral_signup.referral_code.user.email}")
                        # Send notification to referrer (can also be part of award_rewards)
                        send_mail(
                            'You earned referral rewards!',
                            f'Congratulations! You earned rewards because {self.email} became a paying customer.',
                            settings.DEFAULT_FROM_EMAIL,
                            [referral_signup.referral_code.user.email],
                            fail_silently=True,
                        )
                    else:
                        logger.error(f"Failed to award referral rewards via User.award_referral_points for {self.email}")
            else:
                logger.info(f"User {self.email} was not referred or referral_signup_info not found.")

        except Exception as e:
            logger.error(f"Error in User.award_referral_points for {self.email}: {e}", exc_info=True)


    def get_referral_stats(self):
        """Get user's referral statistics"""
        from referrals.models import ReferralCode # Example if needed directly
        try:
            # 'referralcode' is the default related_name for a OneToOneField from ReferralCode to User
            # If you defined a custom related_name on ReferralCode.user, use that.
            # e.g., if ReferralCode.user = OneToOneField(User, related_name='my_referral_code_obj')
            # then use self.my_referral_code_obj
            referral_code_obj = self.referral_code_obj # Assuming related_name='referral_code_obj' on ReferralCode.user
            
            # Points earned should ideally come from UserPoints model or a consolidated source
            # self.profile.ai_points might not be the sole source of "referral points"
            # For now, using what's available:
            return {
                'code': referral_code_obj.code,
                'total_referrals': self.profile.total_referrals, # This needs to be updated by a signal or task
                'successful_referrals': self.profile.successful_referrals, # Also needs updating
                'points_earned': self.profile.ai_points, # Or UserPoints.balance
                'share_url': f"{settings.BASE_URL}/join/{referral_code_obj.code}/" # Ensure settings.BASE_URL is correct
            }
        except ReferralCode.DoesNotExist:
            logger.warning(f"ReferralCode does not exist for user {self.email} in get_referral_stats.")
            return None
        except AttributeError: # Handles case where self.referral_code_obj might not exist if not created yet
            logger.warning(f"ReferralCode attribute not found for user {self.email} in get_referral_stats.")
            return None
        except Exception as e:
            logger.error(f"Error in get_referral_stats for {self.email}: {e}", exc_info=True)
            return None

    def ensure_referral_code(self): # Renamed for clarity
        """
        Ensures a referral code exists for this user, creating one if necessary.
        Uses get_or_create to be idempotent and avoid IntegrityError.
        """
        from referrals.models import ReferralCode # Already imported at top
        code_obj, created = ReferralCode.objects.get_or_create(user=self)
        if created:
            logger.info(f"ReferralCode object created for user {self.email}. Associated code: {code_obj.code}")
        # else:
            # logger.info(f"ReferralCode object already existed for user {self.email}. Associated code: {code_obj.code}")
        return code_obj


class UserProfile(models.Model):
    SPECIALIZATION_CHOICES = [
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

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    current_country = CountryField(blank=True, null=True)
    target_uk_region = models.CharField(max_length=50, choices=UK_REGION_CHOICES, blank=True, null=True)
    tech_specializations = models.JSONField(default=list, blank=True)
    
    github_profile = models.URLField(max_length=200, blank=True, null=True)
    linkedin_profile = models.URLField(max_length=200, blank=True, null=True)
    portfolio_website = models.URLField(max_length=200, blank=True, null=True)

    assessment_completed = models.BooleanField(default=False)
    documents_completed = models.BooleanField(default=False)
    document_status = models.JSONField(default=dict, blank=True)
    expert_review_completed = models.BooleanField(default=False)
    application_submitted = models.BooleanField(default=False)

    ai_queries_used = models.IntegerField(default=0)
    ai_queries_limit = models.IntegerField(default=5) # Consider if this should be on UserPoints or a Subscription model
    consultation_credits = models.IntegerField(default=0)

    # ai_points is being deprecated in favor of UserPoints model.
    # This field can be removed after migration if UserPoints is fully adopted.
    # ai_points = models.IntegerField(default=0) 
    lifetime_points = models.IntegerField(default=0)
    total_referrals = models.IntegerField(default=0)
    successful_referrals = models.IntegerField(default=0)
    is_paid_user = models.BooleanField(default=False)
    available_free_uses = models.IntegerField(default=0, help_text="Number of free feature uses earned from referrals.")

    def get_progress_percentage(self):
        completed_steps = sum([
            self.assessment_completed,
            self.documents_completed,
            self.expert_review_completed,
            self.application_submitted
        ])
        return (completed_steps / 4) * 100

    def update_document_status(self, doc_type, status):
        if not self.document_status:
            self.document_status = {}
        self.document_status[doc_type] = status
        self.save(update_fields=['document_status']) # Be specific

    def check_documents_completed(self):
        if not self.document_status:
            return False
        required_docs = ['personal_statement', 'cv'] # Define this more centrally if it varies
        return all(doc in self.document_status and self.document_status[doc] == 'completed'
                  for doc in required_docs)

    def __str__(self):
        return f"Profile for {self.user.email}"

    def update_referral_stats(self):
        """Update referral statistics based on ReferralSignup records."""
        from referrals.models import ReferralSignup, ReferralCode # Import here
        try:
            referral_code_obj = self.user.referral_code_obj 
            self.total_referrals = ReferralSignup.objects.filter(
                referral_code=referral_code_obj
            ).count()
            self.successful_referrals = ReferralSignup.objects.filter(
                referral_code=referral_code_obj,
                has_been_rewarded=True 
            ).count()
            self.save(update_fields=['total_referrals', 'successful_referrals'])
        except ReferralCode.DoesNotExist:
            logger.warning(f"ReferralCode not found for {self.user.email} during update_referral_stats.")
        except AttributeError:
            logger.warning(f"User {self.user.email} does not have referral_code_obj for update_referral_stats.")


    def award_points(self, points, reason=None):
        from document_manager.models import UserPoints # Import here
        user_points, created = UserPoints.objects.get_or_create(user=self.user)
        user_points.balance += points
        user_points.save()
        logger.info(f"Awarded {points} points to {self.user.email} via UserProfile.award_points. New UserPoints balance: {user_points.balance}")

        Activity.objects.create( # Ensure Activity is defined or imported
            user=self.user,
            type='referral_reward', 
            description=f'Earned {points} AI points' + (f' for {reason}' if reason else '')
        )


class Activity(models.Model):
    ACTIVITY_TYPES = (
        ('document', 'Document'),
        ('ai', 'AI Assistant'),
        ('assessment', 'Assessment'),
        ('expert', 'Expert Session'),
        ('notification', 'Notification'),
        ('referral_reward', 'Referral Reward'),
        ('points_awarded', 'Points Awarded'), # Added for flexibility
        ('free_use_awarded', 'Free Use Awarded'), # Added
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.CharField(max_length=255)
    related_object_id = models.IntegerField(null=True, blank=True)
    related_object_type = models.CharField(max_length=50, null=True, blank=True) # Consider ContentType framework
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Activities'

    def __str__(self):
        return f"{self.type} for {self.user.email} - {self.description[:50]}"

class AIConversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_conversations')
    query = models.TextField()
    response = models.TextField()
    category = models.CharField(max_length=50, blank=True)
    feedback_helpful = models.BooleanField(null=True)
    user_feedback = models.TextField(blank=True)
    conversation_context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Conversation with {self.user.email} at {self.created_at}"


class ContactMessage(models.Model):
    STATUS_CHOICES = (
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    )
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='resolved_messages'
    )
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Contact Message'
        verbose_name_plural = 'Contact Messages'
    def __str__(self):
        return f"{self.subject} - {self.email}"
    def mark_resolved(self, user):
        self.status = 'resolved'
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.save(update_fields=['status', 'resolved_at', 'resolved_by'])


# --- Consolidated Signal Handler ---
@receiver(post_save, sender=User)
def post_save_user_receiver(sender, instance, created, **kwargs):
    if created:
        logger.info(f"New user created: {instance.email}. Initializing profile, referral code, and points.")
        profile, profile_created = UserProfile.objects.get_or_create(user=instance)
        if profile_created:
            logger.info(f"UserProfile created for {instance.email}.")
            Activity.objects.create(
                user=instance,
                type='notification', # Consider a more specific type like 'account_created'
                description='Welcome! Your profile has been created.'
            )
        
        # Ensure referral code exists
        instance.ensure_referral_code() # This method is on your User model

        # Create UserPoints and set initial balance
        from document_manager.models import UserPoints
        user_points, points_were_actually_created_by_this_call = UserPoints.objects.get_or_create(user=instance)

        # Check if this is a truly new user scenario for points
        # (e.g., points record was just made, or exists but is empty)
        if points_were_actually_created_by_this_call or \
           (user_points.balance == 0 and user_points.lifetime_points == 0):
            
            user_points.balance = 3
            user_points.lifetime_points = 3 # Initialize lifetime points as well
            user_points.save() # Save the changes
            
            logger.info(f"Initial 3 UserPoints set for {instance.email}. New balance: 3")
            Activity.objects.create(
                user=instance,
                type='points_awarded', # This type seems fine
                description='Welcome! You received 3 free AI points.'
            )
        elif user_points.balance != 3 : # It existed but wasn't 3 (and not 0,0 which was handled above)
             logger.warning(f"UserPoints for {instance.email} already existed with balance {user_points.balance}. Initial 3 points not re-applied.")