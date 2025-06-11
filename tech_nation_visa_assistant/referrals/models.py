# referrals/models.py

from django.db import models
from django.conf import settings
# import uuid # Not currently used in the snippet, can be removed if not needed elsewhere
from django.utils import timezone as django_timezone
import logging
from django.db import transaction
from django.utils.crypto import get_random_string

# from accounts.models import UserProfile # Correctly removed
# from document_manager.models import UserPoints # Not needed here if only free uses are awarded

logger = logging.getLogger(__name__)

class ReferralCode(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_code_obj')
    code = models.CharField(max_length=10, unique=True, blank=True)
    clicks = models.IntegerField(default=0)
    successful_referrals = models.IntegerField(default=0) # Tracks successful referrals for this code
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Referral code {self.code} for {self.user.email}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = get_random_string(8)
        super().save(*args, **kwargs)

    def get_share_url(self):
        return f"{settings.BASE_URL}/join/{self.code}/"

    def get_whatsapp_share_text(self):
        return (
            "Join me on Tech Nation Visa Assistant! "
            f"Use my referral code {self.code} to get started. "
            f"{self.get_share_url()}"
        )
    
    def get_email_share_text(self):
        user_full_name = self.user.get_full_name() if hasattr(self.user, 'get_full_name') else self.user.email
        return {
            'subject': 'Join me on Tech Nation Visa Assistant',
            'body': (
                f"Hi!\n\n"
                f"I'm using Tech Nation Visa Assistant to help with my Global Talent Visa application. "
                f"I thought you might find it useful too.\n\n"
                f"Use my referral code {self.code} when you sign up: {self.get_share_url()}\n\n"
                f"Best regards,\n"
                f"{user_full_name}"
            )
        }

    def get_twitter_share_text(self):
        return (
            "I'm using Tech Nation Visa Assistant for my Global Talent Visa application. "
            f"Join using my referral code: {self.code}"
        )


class ReferralSignup(models.Model):
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE, related_name='signups')
    # If a user can only be referred ONCE in their lifetime, this should be OneToOneField.
    # If they can sign up, then later be referred by someone else (unlikely for a single platform), ForeignKey is okay.
    # Given 'referral_signup_info' on User, OneToOneField is more idiomatic.
    # For now, sticking to your provided ForeignKey.
    referred_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_signup_info')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    # 'points_awarded' might be better named 'reward_processed_at' or similar if no points are involved.
    # For now, keeping it as is, but it signifies that the reward logic for this event ran.
    points_awarded = models.BooleanField(default=False, help_text="Indicates if the reward logic for this referral becoming a paying user has been processed.")
    points_awarded_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    has_been_rewarded = models.BooleanField(default=False, help_text="Ensures rewards for this specific signup (referred user becoming paying) are given only once.")
    free_use_granted = models.BooleanField(default=False, help_text="True if the one-time free feature use has been granted to the referrer for this specific referral.")

    class Meta:
        unique_together = ['referral_code', 'referred_user']

    def __str__(self):
        return f"Referral signup by {self.referred_user.email} using code {self.referral_code.code}"

    def award_rewards(self):
        """
        Awards one free feature use to the referrer when the referred user
        becomes a paying customer.
        This method should be called when the referred_user makes their first qualifying payment.
        """
        if self.has_been_rewarded:
            logger.info(f"Referral {self.id} (referred: {self.referred_user.email}) has already been rewarded. Skipping.")
            return False

        try:
            logger.info(f"Processing rewards for referral {self.id} (referred: {self.referred_user.email}, referrer: {self.referral_code.user.email})")
            with transaction.atomic():
                referrer = self.referral_code.user
                
                # Dynamically import Activity model to avoid potential circular imports at module level
                from accounts.models import Activity, UserProfile

                # Ensure referrer has a profile. This should ideally be guaranteed by signals.
                try:
                    referrer_profile = referrer.profile
                except UserProfile.DoesNotExist: # More specific exception
                    logger.error(f"Referrer {referrer.email} does not have a UserProfile. Cannot award free use.")
                    # Optionally create profile on the fly if absolutely necessary, though signals are better.
                    # referrer_profile = UserProfile.objects.create(user=referrer)
                    # logger.info(f"UserProfile created on-the-fly for {referrer.email} in award_rewards.")
                    return False # Cannot proceed without a profile to update

                profile_fields_to_update = []

                # Grant one-time free feature use if not already granted from THIS specific signup
                if not self.free_use_granted: # Check flag on this signup instance
                    referrer_profile.available_free_uses = getattr(referrer_profile, 'available_free_uses', 0) + 1
                    self.free_use_granted = True # Mark it on this signup
                    if 'available_free_uses' not in profile_fields_to_update:
                        profile_fields_to_update.append('available_free_uses')
                    logger.info(f"Granted one free feature use to {referrer.email} from referral {self.id}. New free uses: {referrer_profile.available_free_uses}")
                    
                    # Create an Activity log for the free use awarded
                    Activity.objects.create(
                        user=referrer,
                        type='free_use_awarded',
                        description=f'Earned 1 free feature use from referral of {self.referred_user.email}.'
                    )
                else:
                    logger.info(f"Free use already granted for this specific referral signup {self.id}. Skipping free use increment.")


                if profile_fields_to_update: # Only save if specific fields on profile were changed
                    referrer_profile.save(update_fields=profile_fields_to_update)

                # Update ReferralSignup status
                self.points_awarded = True # Signifies reward logic was processed
                self.has_been_rewarded = True # Prevents re-rewarding for this specific signup
                self.points_awarded_at = django_timezone.now()
                # free_use_granted is already set above
                self.save(update_fields=['points_awarded', 'has_been_rewarded', 'points_awarded_at', 'free_use_granted'])

                # Update successful referrals count on the ReferralCode
                # This ensures the ReferralCode object reflects the count of rewarded signups.
                self.referral_code.successful_referrals = ReferralSignup.objects.filter(
                    referral_code=self.referral_code,
                    has_been_rewarded=True
                ).count() # Recalculate for accuracy
                self.referral_code.save(update_fields=['successful_referrals'])
                logger.info(f"Updated successful_referrals for code {self.referral_code.code} to {self.referral_code.successful_referrals}")
                
                # Also update the referrer's profile successful_referrals count
                # This assumes UserProfile.successful_referrals is the primary display stat for the user
                referrer_profile.successful_referrals = self.referral_code.successful_referrals
                referrer_profile.save(update_fields=['successful_referrals'])


            logger.info(f"Successfully awarded rewards (1 free use) for referral {self.id} to {referrer.email}.")
            return True
        except Exception as e:
            logger.error(f"Error awarding rewards for referral {self.id}: {e}", exc_info=True)
            # Transaction will roll back
            return False  


class ReferralClick(models.Model):
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE, related_name='clicks_log')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Click on {self.referral_code.code} at {self.timestamp}"