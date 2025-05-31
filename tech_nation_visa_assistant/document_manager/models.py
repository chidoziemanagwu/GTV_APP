from django.db import models
from accounts.models import User

class EligibilityCriteria(models.Model):
    TYPE_CHOICES = (
        ('mandatory', 'Mandatory'),
        ('optional', 'Optional'),
    )
    PATH_CHOICES = (
        ('talent', 'Exceptional Talent'),
        ('promise', 'Exceptional Promise'),
        ('both', 'Both Paths'),
    )

    name = models.CharField(max_length=200)
    description = models.TextField()
    criteria_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    applicable_path = models.CharField(max_length=10, choices=PATH_CHOICES)
    number_of_documents = models.IntegerField(default=2)
    notion_link = models.URLField(blank=True)

    def __str__(self):
        return f"{self.criteria_type.title()} - {self.name}"

# document_manager/models.py

class Document(models.Model):
    STATUS_CHOICES = (
        ('not_started', 'Not Started'),
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('reviewing', 'Under Review'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    )

    TYPE_CHOICES = (
        ('personal_statement', 'Personal Statement'),
        ('cv', 'CV'),
        ('recommendation', 'Recommendation Letter'),
        ('evidence', 'Evidence Document'),
        ('other', 'Other'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    document_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    related_criteria = models.ForeignKey(
        EligibilityCriteria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Content and File
    content = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='user_documents/', null=True, blank=True)

    # Status and Metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='not_started')
    is_generated = models.BooleanField(default=False)
    generation_prompt = models.TextField(blank=True, null=True)

    # Document Analysis
    word_count = models.IntegerField(default=0)
    page_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    source_cv = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_documents',
        help_text="If this is a personal statement, links to the CV used to generate it"
    )

    original_file = models.FileField(
        upload_to='original_documents/',
        null=True,
        blank=True,
        help_text="Original uploaded document"
    )

    generated_file = models.FileField(
        upload_to='generated_documents/',
        null=True,
        blank=True,
        help_text="Generated document in DOCX format"
    )

    is_chosen = models.BooleanField(
        default=False,
        help_text="Indicates if this document is the user's chosen version for submission"
    )

    notes = models.TextField(blank=True, null=True)  # Add this line
    
    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} - {self.get_document_type_display()}"

    @property
    def has_original_file(self):
        return bool(self.original_file)

    def generate_docx(self):
        """Generate a DOCX file with disclaimer"""
        from docx import Document as DocxDocument

        doc = DocxDocument()

        # Add disclaimer
        disclaimer = doc.add_paragraph()
        disclaimer.add_run("DISCLAIMER").bold = True
        doc.add_paragraph(
            "This document is auto-generated for sample purposes only. "
            "It should be thoroughly reviewed, customized, and edited to reflect "
            "your personal experiences and achievements. Do not submit this "
            "document as-is for your visa application."
        )

        # Add a divider
        doc.add_paragraph("=" * 50)

        # Add the main content
        doc.add_paragraph(self.content)

        # Save the file
        filename = f"{self.title}_{self.id}.docx"
        filepath = f"generated_documents/{filename}"
        doc.save(filepath)

        # Update the generated_file field
        self.generated_file.name = filepath
        self.save()

    def get_file_extension(self):
        if self.file:
            return self.file.name.split('.')[-1].lower()
        return None



class DocumentComment(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment on {self.document.title}"
    



# Add this to your models.py
class UserPoints(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='points')
    balance = models.IntegerField(default=0)
    lifetime_points = models.IntegerField(default=0)
    last_purchase = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.balance} points"

    def add_points(self, amount):
        self.balance += amount
        self.lifetime_points += amount

        # Update the user's profile as well
        try:
            profile = self.user.profile
            profile.ai_points = self.balance
            profile.lifetime_points = self.lifetime_points
            profile.is_paid_user = True  # Set to paid user when points are added
            profile.save()
        except Exception as e:
            print(f"Error updating profile points: {e}")

        self.save()

    def use_points(self, amount):
        if self.balance >= amount:
            self.balance -= amount
            self.save()

            # Update the user's profile
            try:
                profile = self.user.profile
                profile.ai_points = self.balance

                # If points are depleted, update paid status
                if self.balance <= 0:
                    profile.is_paid_user = False

                profile.save()
            except Exception as e:
                print(f"Error updating profile points: {e}")

            return True
        return False


class PointsPackage(models.Model):
    name = models.CharField(max_length=100)
    points = models.IntegerField()
    price = models.DecimalField(max_digits=6, decimal_places=2)
    description = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} - {self.points} points (£{self.price})"
    

class PointsTransaction(models.Model):
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='points_transactions')
    package = models.ForeignKey(PointsPackage, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    points = models.IntegerField()
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_checkout_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.points} points - {self.get_payment_status_display()}"
    


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=UserPoints)
def sync_points_with_profile(sender, instance, **kwargs):
    """Sync points between UserPoints and UserProfile"""
    try:
        profile = instance.user.profile
        profile.ai_points = instance.balance
        profile.lifetime_points = instance.lifetime_points
        profile.is_paid_user = instance.balance > 0
        profile.save()
    except Exception as e:
        print(f"Error syncing points with profile: {e}")


@receiver(post_save, sender='accounts.UserProfile')
def create_user_points(sender, instance, created, **kwargs):
    """Create UserPoints when a UserProfile is created"""
    if created:
        from document_manager.models import UserPoints
        try:
            UserPoints.objects.get(user=instance.user)
        except UserPoints.DoesNotExist:
            UserPoints.objects.create(
                user=instance.user,
                balance=instance.ai_points,
                lifetime_points=instance.lifetime_points
            )



from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

def award_referral_points(user):
    """
    Award referral points to the referrer when a user makes a purchase

    Args:
        user: The user who made the purchase
    """
    from referrals.models import ReferralSignup
    from document_manager.models import UserPoints

    try:
        # Find if this user was referred by someone
        referral = ReferralSignup.objects.get(referred_user=user)

        if not referral.points_awarded:  # Only award points once
            # Get the referrer
            referrer = referral.referral_code.user

            # Award bonus points to the referrer
            referrer_points, _ = UserPoints.objects.get_or_create(user=referrer)
            referrer_points.add_points(3)  # Award 3 bonus points

            # Mark the referral as converted with points awarded
            referral.points_awarded = True
            referral.points_awarded_at = timezone.now()
            referral.save()

            logger.info(f"Awarded 3 referral points to {referrer.username} for {user.username}'s purchase")
            return True
        else:
            logger.info(f"Referral points already awarded for {user.username}")
            return False

    except ReferralSignup.DoesNotExist:
        # User wasn't referred
        logger.info(f"User {user.username} made a purchase but wasn't referred")
        return False
    except Exception as e:
        logger.error(f"Error processing referral bonus: {str(e)}")
        return False