from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone as django_timezone
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

class ReferralCode(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code = models.CharField(max_length=20, unique=True)
    clicks = models.IntegerField(default=0)
    successful_referrals = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Referral code {self.code} for {self.user.email}"

    def save(self, *args, **kwargs):
        if not self.code:
            # Generate a unique code if one doesn't exist
            self.code = str(uuid.uuid4())[:8]
        super().save(*args, **kwargs)

    def get_share_url(self):
        """Get the full URL for sharing"""
        return f"{settings.BASE_URL}/join/{self.code}/"

    def get_whatsapp_share_text(self):
        """Get the text for WhatsApp sharing"""
        return (
            "Join me on Tech Nation Visa Assistant! "
            f"Use my referral code {self.code} to get started. "
            f"{self.get_share_url()}"
        )
    
    
    def get_email_share_text(self):
        """Get the text for email sharing"""
        return {
            'subject': 'Join me on Tech Nation Visa Assistant',
            'body': (
                f"Hi!\n\n"
                f"I'm using Tech Nation Visa Assistant to help with my Global Talent Visa application. "
                f"I thought you might find it useful too.\n\n"
                f"Use my referral code {self.code} when you sign up: {self.get_share_url()}\n\n"
                f"Best regards,\n"
                f"{self.user.get_full_name() or self.user.email}"
            )
        }

    def get_twitter_share_text(self):
        """Get the text for Twitter sharing"""
        return (
            "I'm using Tech Nation Visa Assistant for my Global Talent Visa application. "
            f"Join using my referral code: {self.code}"
        )


class ReferralSignup(models.Model):
    referral_code = models.ForeignKey(ReferralCode, on_delete=models.CASCADE, related_name='signups')
    referred_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referred_signups')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    points_awarded = models.BooleanField(default=False)  # This stays as is - indicates if points were ever awarded
    points_awarded_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Add this new field to track if this referral has been used for points
    has_been_rewarded = models.BooleanField(default=False)

    class Meta:
        unique_together = ['referral_code', 'referred_user']

    def __str__(self):
        return f"Referral signup by {self.referred_user.email} using code {self.referral_code.code}"

    def award_points(self):
        """Award points to the referrer when a referred user makes a purchase"""
        # Only award points if this referral has never been rewarded before
        if not self.has_been_rewarded:
            try:
                logger.info(f"Attempting to award points for referral {self.id}")
                with transaction.atomic():
                    # Mark as awarded and rewarded
                    self.points_awarded = True
                    self.has_been_rewarded = True  # Set this to True to prevent future rewards
                    self.points_awarded_at = django_timezone.now()
                    self.save()
                    logger.info(f"Marked referral {self.id} as awarded")

                    # Update successful referrals count
                    self.referral_code.successful_referrals += 1
                    self.referral_code.save()
                    logger.info(f"Updated successful referrals count for code {self.referral_code.code}")

                    # Award points to referrer
                    referrer = self.referral_code.user
                    logger.info(f"Awarding points to referrer {referrer.username}")

                    # We don't update UserPoints here anymore, as those are the main points
                    # Instead, we only update the profile's referral points

                    # Update profile directly with referral points
                    try:
                        # Only update the profile's referral-specific fields
                        # Don't modify the main ai_points balance
                        referrer.profile.is_paid_user = True
                        referrer.profile.save()
                        logger.info(f"Updated referrer profile status for {referrer.username}")
                    except Exception as e:
                        logger.error(f"Error updating profile: {e}")
                        # Re-raise to trigger transaction rollback if profile update fails
                        raise

                logger.info(f"Successfully awarded referral for {referrer.username} from {self.referred_user.username}'s purchase")
                return True
            except Exception as e:
                logger.error(f"Error awarding referral points: {e}")
                return False
        else:
            logger.info(f"This referral {self.id} has already been rewarded once. No additional points awarded.")
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