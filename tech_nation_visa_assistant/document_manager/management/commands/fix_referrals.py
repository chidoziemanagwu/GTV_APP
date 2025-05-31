from django.core.management.base import BaseCommand
from django.utils import timezone
from referrals.models import ReferralSignup
from document_manager.models import PointsTransaction, UserPoints

class Command(BaseCommand):
    help = 'Fix referral points for users who have made purchases but referrers have not received points'

    def handle(self, *args, **options):
        # Get all referrals
        all_referrals = ReferralSignup.objects.all()
        self.stdout.write(f"Found {all_referrals.count()} total referrals")

        # Process each referral
        for referral in all_referrals:
            referred_user = referral.referred_user
            referrer = referral.referral_code.user

            self.stdout.write(f"Processing referral: {referrer.username} referred {referred_user.username}")

            # Check if the referred user has made a purchase
            has_purchase = PointsTransaction.objects.filter(
                user=referred_user,
                payment_status='completed'
            ).exists()

            if has_purchase:
                self.stdout.write(f"  - User {referred_user.username} has made a purchase")

                # Update referral status if not already marked
                if not referral.points_awarded:
                    referral.points_awarded = True
                    referral.points_awarded_at = timezone.now()
                    referral.save()
                    self.stdout.write(self.style.SUCCESS(f"  - Updated referral status to points_awarded=True"))
                else:
                    self.stdout.write(f"  - Referral already marked as points_awarded=True")

                # Check if referrer has received points
                referrer_points, _ = UserPoints.objects.get_or_create(user=referrer)

                # Award points if needed (we'll add them regardless to ensure they're counted)
                referrer_points.add_points(3)
                self.stdout.write(self.style.SUCCESS(f"  - Awarded 3 points to {referrer.username}"))

                # Update profile as well
                try:
                    referrer.profile.ai_points += 3
                    referrer.profile.save()
                    self.stdout.write(self.style.SUCCESS(f"  - Updated profile points for {referrer.username}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  - Error updating profile: {e}"))
            else:
                self.stdout.write(f"  - User {referred_user.username} has not made a purchase yet")

        self.stdout.write(self.style.SUCCESS("Referral fix completed"))