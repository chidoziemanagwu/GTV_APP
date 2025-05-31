from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone
import logging

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
    points_awarded = models.BooleanField(default=False)
    points_awarded_at = models.DateTimeField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['referral_code', 'referred_user']

    def __str__(self):
        return f"Referral signup by {self.referred_user.email} using code {self.referral_code.code}"

    def award_points(self):
        """Award points to the referrer when a referred user makes a purchase"""
        if not self.points_awarded:
            try:
                # Mark as awarded
                self.points_awarded = True
                self.points_awarded_at = timezone.now()
                self.save()

                # Update successful referrals count
                self.referral_code.successful_referrals += 1
                self.referral_code.save()

                # Award points to referrer
                referrer = self.referral_code.user

                # Update UserPoints
                from document_manager.models import UserPoints
                referrer_points, _ = UserPoints.objects.get_or_create(user=referrer)
                referrer_points.add_points(3)  # Award 3 bonus points

                # Also update profile directly as a backup
                try:
                    referrer.profile.ai_points += 3
                    referrer.profile.lifetime_points += 3
                    referrer.profile.save()
                except Exception as e:
                    logger.error(f"Error updating profile points: {e}")

                logger.info(f"Awarded 3 referral points to {referrer.username} for {self.referred_user.username}'s purchase")
                return True
            except Exception as e:
                logger.error(f"Error awarding referral points: {e}")
                return False
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