# expert_marketplace/management/commands/process_weekly_payouts.py

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Sum

from expert_marketplace.models import Expert, ExpertEarning
from expert_marketplace.stripe_service import process_expert_payouts

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Processes weekly payouts for experts for earnings accrued from Monday to Friday.'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # This command is designed to run on Friday.
        # We'll define the week as Monday to Friday, ending on the day the command runs.
        if now.weekday() != 4: # Monday is 0, Friday is 4
            self.stdout.write(self.style.WARNING(
                f"This command is intended to run on Fridays. Today is {now.strftime('%A')}. "
                f"If run manually on another day, it will process for the week ending on the *upcoming* or *just passed* Friday."
            ))
            # For a scheduled job, this check is less critical but good for manual runs.
            # Let's find the Friday of the current/most recent week.
            friday_of_processing_week = now - timezone.timedelta(days=now.weekday() - 4)
        else:
            friday_of_processing_week = now

        start_of_week = friday_of_processing_week - timezone.timedelta(days=4) # Monday

        # Define the period for earnings calculation (whole days)
        start_of_day_start_of_week = timezone.make_aware(timezone.datetime.combine(start_of_week.date(), timezone.datetime.min.time()))
        end_of_day_end_of_week = timezone.make_aware(timezone.datetime.combine(friday_of_processing_week.date(), timezone.datetime.max.time()))

        self.stdout.write(self.style.SUCCESS(
            f"Processing weekly payouts for earnings calculated from: {start_of_day_start_of_week.strftime('%Y-%m-%d')} "
            f"to {end_of_day_end_of_week.strftime('%Y-%m-%d')}."
        ))

        # Get experts who have pending earnings within this period
        experts_with_pending_earnings = Expert.objects.filter(
            all_earnings_records__status=ExpertEarning.PENDING,
            all_earnings_records__calculated_at__gte=start_of_day_start_of_week,
            all_earnings_records__calculated_at__lte=end_of_day_end_of_week,
            is_active=True # Only active experts
        ).distinct()

        if not experts_with_pending_earnings.exists():
            self.stdout.write(self.style.SUCCESS("No experts with pending earnings found for this period."))
            return

        payout_count_success = 0
        payout_count_failed = 0

        for expert in experts_with_pending_earnings:
            if not expert.stripe_account_id or not expert.stripe_payouts_enabled():
                logger.warning(f"Skipping payout for expert {expert.id} ({expert.full_name}): Stripe account not ready (ID: {expert.stripe_account_id}, Payouts Enabled: {expert.stripe_payouts_enabled()}).")
                self.stdout.write(self.style.WARNING(f"Skipping expert {expert.full_name}: Stripe account not ready."))
                continue

            earnings_for_expert_this_week = ExpertEarning.objects.filter(
                expert=expert,
                status=ExpertEarning.PENDING,
                calculated_at__gte=start_of_day_start_of_week,
                calculated_at__lte=end_of_day_end_of_week,
                amount__gt=Decimal('0.00') # Only positive amounts
            )

            if not earnings_for_expert_this_week.exists():
                logger.info(f"No positive pending earnings this week for expert {expert.id} ({expert.full_name}) after specific filtering.")
                continue

            # The process_expert_payouts function will sum these up.
            # It also handles the case where the net amount might be zero after fees (though no fee here).
            
            self.stdout.write(f"Attempting payout for {expert.full_name} (ID: {expert.id}) for {earnings_for_expert_this_week.count()} earning(s).")

            payout_description = f"Weekly Payout for {expert.full_name} - Week ending {friday_of_processing_week.strftime('%Y-%m-%d')}"
            
            payout_result = process_expert_payouts(
                expert_profile=expert,
                earnings_to_pay=list(earnings_for_expert_this_week),
                is_instant_request=False, # This is a scheduled, non-instant payout (no fee)
                payout_description=payout_description
            )

            if payout_result.get('success'):
                self.stdout.write(self.style.SUCCESS(f"Successfully processed payout for {expert.full_name}. Transfer ID: {payout_result.get('transfer_id')}"))
                payout_count_success += 1
            else:
                self.stdout.write(self.style.ERROR(f"Failed to process payout for {expert.full_name}. Error: {payout_result.get('error')}"))
                logger.error(f"Weekly Payout Failed for Expert ID {expert.id}: {payout_result.get('error')}")
                payout_count_failed += 1
        
        self.stdout.write(self.style.SUCCESS(f"Weekly payout processing complete. Successful: {payout_count_success}, Failed: {payout_count_failed}."))