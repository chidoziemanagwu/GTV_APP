# accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django_countries.fields import CountryField
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


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
        try:
            # Get the referral signup for this user
            referral_signup = self.referred_signups.first()

            if referral_signup and not referral_signup.points_awarded:
                # Get the referrer
                referrer = referral_signup.referral_code.user

                # Award 3 points
                referrer.profile.ai_points += 3
                referrer.profile.save()

                # Mark points as awarded
                referral_signup.points_awarded = True
                referral_signup.points_awarded_at = timezone.now()
                referral_signup.save()

                # Send notification to referrer
                send_mail(
                    'You earned referral points!',
                    f'Congratulations! You earned 3 AI points because {self.email} became a paying customer.',
                    settings.DEFAULT_FROM_EMAIL,
                    [referrer.email],
                    fail_silently=True,
                )

        except Exception as e:
            # Log the error but don't raise it
            print(f"Error awarding referral points: {e}")



    def get_referral_stats(self):
        """Get user's referral statistics"""
        try:
            referral_code = self.referralcode
            return {
                'code': referral_code.code,
                'total_referrals': self.profile.total_referrals,
                'successful_referrals': self.profile.successful_referrals,
                'points_earned': self.profile.ai_points,
                'share_url': f"{settings.BASE_URL}/join/{referral_code.code}/"
            }
        except:
            return None

    def create_referral_code(self):
        """Create a referral code for the user if they don't have one"""
        from referrals.models import ReferralCode
        if not hasattr(self, 'referralcode'):
            ReferralCode.objects.create(user=self)

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
    
    # Personal Information
    current_country = CountryField(blank=True, null=True)
    target_uk_region = models.CharField(max_length=50, choices=UK_REGION_CHOICES, blank=True, null=True)
    tech_specializations = models.JSONField(default=list, blank=True)
    
    # Professional Links
    github_profile = models.URLField(max_length=200, blank=True, null=True)
    linkedin_profile = models.URLField(max_length=200, blank=True, null=True)
    portfolio_website = models.URLField(max_length=200, blank=True, null=True)

    # Progress Tracking
    assessment_completed = models.BooleanField(default=False)
    documents_completed = models.BooleanField(default=False)
    document_status = models.JSONField(default=dict, blank=True)
    expert_review_completed = models.BooleanField(default=False)
    application_submitted = models.BooleanField(default=False)

    # AI Assistant Usage
    ai_queries_used = models.IntegerField(default=0)
    ai_queries_limit = models.IntegerField(default=5)
    consultation_credits = models.IntegerField(default=0)

    # Referral System
    ai_points = models.IntegerField(default=0)
    lifetime_points = models.IntegerField(default=0)  # Add this field
    total_referrals = models.IntegerField(default=0)
    successful_referrals = models.IntegerField(default=0)
    is_paid_user = models.BooleanField(default=False)


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
        self.save()

    def check_documents_completed(self):
        if not self.document_status:
            return False
        required_docs = ['personal_statement', 'cv']
        return all(doc in self.document_status and self.document_status[doc] == 'completed'
                  for doc in required_docs)

    def __str__(self):
        return f"Profile for {self.user.email}"

    

    def update_referral_stats(self):
        """Update referral statistics"""
        from referrals.models import ReferralCode, ReferralSignup
        try:
            referral_code = ReferralCode.objects.get(user=self.user)
            self.total_referrals = ReferralSignup.objects.filter(
                referral_code=referral_code
            ).count()
            self.successful_referrals = ReferralSignup.objects.filter(
                referral_code=referral_code,
                points_awarded=True
            ).count()
            self.save()
        except ReferralCode.DoesNotExist:
            pass

    def award_points(self, points, reason=None):
        """Award AI points to the user"""
        self.ai_points += points
        self.save()

        # Create activity record
        Activity.objects.create(
            user=self.user,
            type='referral_reward',
            description=f'Earned {points} AI points' + (f' for {reason}' if reason else '')
        )

# class Document(models.Model):
#     DOCUMENT_TYPES = [
#         ('personal_statement', 'Personal Statement'),
#         ('cv', 'CV'),
#         ('recommendation', 'Recommendation Letter'),
#     ]

#     STATUS_CHOICES = [
#         ('draft', 'Draft'),
#         ('reviewing', 'Under Review'),
#         ('completed', 'Completed'),
#         ('archived', 'Archived'),
#     ]

#     user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
#     title = models.CharField(max_length=255)
#     document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
#     file = models.FileField(upload_to='user_documents/', null=True, blank=True)
#     content = models.TextField(blank=True, null=True)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
#     is_generated = models.BooleanField(default=False)
#     generation_prompt = models.TextField(blank=True, null=True)
    
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         ordering = ['-updated_at']

#     def __str__(self):
#         return f"{self.title} - {self.get_document_type_display()}"

#     def get_file_extension(self):
#         if self.file:
#             return self.file.name.split('.')[-1].lower()
#         return None



class Activity(models.Model):
    ACTIVITY_TYPES = (
        ('document', 'Document'),
        ('ai', 'AI Assistant'),
        ('assessment', 'Assessment'),
        ('expert', 'Expert Session'),
        ('notification', 'Notification'),
        ('referral_reward', 'Referral Reward'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.CharField(max_length=255)
    related_object_id = models.IntegerField(null=True, blank=True)
    related_object_type = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Activities'

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

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a new User is created"""
    if created:
        # Only create a profile if one doesn't already exist
        try:
            UserProfile.objects.get(user=instance)
        except UserProfile.DoesNotExist:
            # Create profile with initial 3 AI points
            profile = UserProfile.objects.create(
                user=instance,
                ai_points=3,  # Give 3 free points to new users
                ai_queries_limit=5  # Set the default query limit
            )

            # Log this activity
            Activity.objects.create(
                user=instance,
                type='notification',
                description='Welcome! You received 3 free AI points.'
            )

        # Create referral code for new users
        instance.create_referral_code()





        
@receiver(post_save, sender=User)
def update_user_profile(sender, instance, **kwargs):
    """Update the UserProfile when the User is updated"""
    if not hasattr(instance, 'profile'):
        try:
            profile = UserProfile.objects.get(user=instance)
            # Create a reference to the profile on the instance
            instance.profile = profile
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            instance.profile = UserProfile.objects.create(user=instance)

    # Save the profile
    instance.profile.save()

    

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Ensure UserProfile is created and saved for all Users."""
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    instance.profile.save()




@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Ensure UserProfile is created and saved for all Users."""
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    instance.profile.save()

@receiver(post_save, sender=User)
def create_user_referral_code(sender, instance, created, **kwargs):
    """Create a referral code for new users"""
    if created:
        instance.create_referral_code()


@receiver(post_save, sender=User)
def update_user_profile(sender, instance, **kwargs):
    """Update the UserProfile when the User is updated"""
    if not hasattr(instance, 'profile'):
        try:
            profile = UserProfile.objects.get(user=instance)
            # Create a reference to the profile on the instance
            instance.profile = profile
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            instance.profile = UserProfile.objects.create(user=instance)

    # Save the profile
    instance.profile.save()