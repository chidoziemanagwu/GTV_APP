# expert_marketplace/management/commands/process_auto_actions.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Sum
from datetime import timedelta
import datetime as dt 
import logging

from expert_marketplace.models import Booking, NoShowDispute, Consultation, ExpertEarning, Expert
# Assuming send_completion_emails and process_stripe_refund are correctly imported or defined
from expert_marketplace.utils import send_completion_emails 
from expert_marketplace.stripe_service import process_refund as process_stripe_refund
from decimal import Decimal

logger = logging.getLogger(__name__)

def subtract_business_days_from_datetime(from_datetime, subtract_days):
    current_datetime = from_datetime
    days_subtracted = 0
    while days_subtracted < subtract_days:
        current_datetime -= timedelta(days=1)
        if current_datetime.weekday() < 5: # Monday is 0, Friday is 4
            days_subtracted += 1
    return current_datetime

class Command(BaseCommand):
    help = 'Processes automatic actions like booking completion and dispute resolution.'

    def _mark_booking_complete_logic(self, booking, completion_reason, consultation_status_override=None):
        """
        Shared logic for marking a booking as complete. Earnings are set to PENDING.
        Immediate payout is NOT handled here.
        """
        booking.status = Booking.COMPLETED # Use model constant
        booking.completed_at = timezone.now()
        booking.completion_notes = completion_reason
        booking.save(update_fields=['status', 'completed_at', 'completion_notes'])

        scheduled_datetime_aware = booking.get_scheduled_datetime_aware()
        consultation_final_status = consultation_status_override if consultation_status_override else Consultation.COMPLETED
        
        Consultation.objects.update_or_create(
            booking=booking,
            defaults={
                'user': booking.user, 
                'expert': booking.expert,
                'scheduled_start_time': scheduled_datetime_aware, 
                'status': consultation_final_status,
                'notes_by_expert': (Consultation.objects.filter(booking=booking).first().notes_by_expert or "") + " " + completion_reason, # Append notes
            }
        )

        if booking.expert:
            booking.calculate_financials(and_save=True)
            booking.refresh_from_db(fields=['expert_earnings', 'platform_fee'])

            if booking.expert_earnings is not None and booking.expert_earnings > Decimal('0.00'):
                earning, created = ExpertEarning.objects.update_or_create(
                    booking=booking,
                    expert=booking.expert,
                    defaults={
                        'amount': booking.expert_earnings,
                        'platform_fee_recorded': booking.platform_fee,
                        'status': ExpertEarning.PENDING, # Always PENDING for weekly payout
                        'calculated_at': timezone.now(),
                        'notes': f"Earning from auto-action: {completion_reason[:100]}"
                    }
                )
                logger.info(f"ExpertEarning {'created' if created else 'updated to PENDING'} for auto-action on booking {booking.id}. Amount: {earning.amount}")
                
                expert_profile = booking.expert
                if created: 
                    expert_profile.total_earnings = (expert_profile.total_earnings or Decimal('0.00')) + earning.amount
                
                # Recalculate pending_payout
                current_pending_sum = ExpertEarning.objects.filter(
                    expert=expert_profile, status=ExpertEarning.PENDING
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                expert_profile.pending_payout = current_pending_sum
                expert_profile.save(update_fields=['total_earnings', 'pending_payout'])
            else:
                logger.warning(f"Auto-action: Expert earnings for booking {booking.id} is zero or None. No ExpertEarning recorded.")
        
        send_completion_emails(booking) # Send notification about completion
        self.stdout.write(self.style.SUCCESS(f"Booking ID {booking.id} marked as complete. Reason: {completion_reason}. Earnings set to PENDING."))
        # NO direct payout call here. Weekly payout command handles this.

    def handle_auto_completion(self):
        self.stdout.write("Processing auto-completion of bookings (3 business day rule)...")
        # Bookings that ended more than 3 business days ago and are still 'confirmed'
        # and have no active disputes.
        cutoff_datetime_for_completion = subtract_business_days_from_datetime(timezone.now(), 3)
        
        bookings_to_check = Booking.objects.filter(
            status=Booking.CONFIRMED,
            scheduled_date__isnull=False,
            scheduled_time__isnull=False
        ).exclude(disputes__status__in=NoShowDispute.ACTIVE_STATUSES) # Exclude bookings with active disputes

        completed_count = 0
        for booking in bookings_to_check:
            session_end_dt_aware = booking.get_session_end_datetime_aware()
            if not session_end_dt_aware:
                logger.warning(f"Booking {booking.id} has no session_end_dt_aware, skipping auto-completion.")
                continue

            if session_end_dt_aware < cutoff_datetime_for_completion:
                self._mark_booking_complete_logic(
                    booking, 
                    "Automatically marked as completed after 3 business days post-session with no issues reported."
                )
                completed_count += 1
        self.stdout.write(f"Auto-completed {completed_count} bookings. Earnings set to PENDING.")

    def handle_dispute_resolution(self):
        self.stdout.write("Processing automatic dispute resolution (3 business day rule)...")
        cutoff_reported_at_datetime = subtract_business_days_from_datetime(timezone.now(), 3)
      
        # --- Client-reported disputes (e.g., expert no-show) leading to refund ---
        client_disputes_to_resolve = NoShowDispute.objects.filter(
            Q(dispute_type__in=[NoShowDispute.EXPERT_NOSHOW, NoShowDispute.QUALITY, NoShowDispute.TECHNICAL, NoShowDispute.OTHER]),
            Q(status__in=[NoShowDispute.PENDING, NoShowDispute.EXPERT_RESPONDED]), # Awaiting admin or auto-resolution
            reported_at__lt=cutoff_reported_at_datetime, 
            resolved_by__isnull=True, 
            booking__status=Booking.DISPUTE 
        )
        refunded_count = 0
        for dispute in client_disputes_to_resolve:
            booking = dispute.booking
            logger.info(f"Auto-resolving client-reported dispute ID {dispute.id} (Booking ID {booking.id}) in favor of client (refund).")

            dispute.status = NoShowDispute.RESOLVED
            dispute.resolution_notes = "Auto-resolved in favor of client after 3 business days with no further admin action. Refund processed."
            dispute.resolved_at = timezone.now()
            dispute.resolved_by_system = True 
            dispute.save()

            # Process refund for the client
            if booking.stripe_payment_intent_id and booking.payment_status == Booking.PAID:
                refund_result = process_stripe_refund(
                    payment_intent_id=booking.stripe_payment_intent_id,
                    amount_to_refund=booking.amount_paid, # Assuming full refund
                    reason="requested_by_customer", # Or a more specific reason
                    booking_id=booking.id,
                    notes=f"Auto-refund due to unresolved dispute: {dispute.get_dispute_type_display()}"
                )
                if refund_result['success']:
                    booking.status = Booking.CANCELLED # Or a specific "Refunded" status
                    booking.cancellation_reason = f"Auto-refunded: {dispute.get_dispute_type_display()}"
                    booking.cancelled_at = timezone.now()
                    booking.payment_status = Booking.REFUNDED
                    booking.save(update_fields=['status', 'cancellation_reason', 'cancelled_at', 'payment_status'])
                    self.stdout.write(self.style.SUCCESS(f"Booking {booking.id} auto-refunded successfully."))
                    refunded_count += 1
                    # Send cancellation/refund email
                    # send_cancellation_emails(booking, cancelled_by_user_type='system')
                else:
                    self.stdout.write(self.style.ERROR(f"Auto-refund FAILED for booking {booking.id}: {refund_result['error']}"))
                    logger.error(f"Auto-refund FAILED for booking {booking.id}: {refund_result['error']}")
            else:
                logger.warning(f"Cannot auto-refund booking {booking.id}: No payment intent or not paid.")
                booking.status = Booking.CANCELLED # Still mark as cancelled if appropriate
                booking.cancellation_reason = f"Dispute resolved, no payment to refund: {dispute.get_dispute_type_display()}"
                booking.save(update_fields=['status', 'cancellation_reason'])


        # --- Expert-reported client no-shows leading to expert payment ---
        expert_disputes_to_resolve = NoShowDispute.objects.filter(
            dispute_type=NoShowDispute.CLIENT_NOSHOW,
            status=NoShowDispute.PENDING, # Only pending ones not yet addressed by client/admin
            reported_at__lt=cutoff_reported_at_datetime, 
            resolved_by__isnull=True, 
            booking__status=Booking.DISPUTE 
        )
        noshow_completed_count = 0
        for dispute in expert_disputes_to_resolve:
            booking = dispute.booking
            logger.info(f"Auto-resolving expert-reported client no-show. Dispute ID {dispute.id} (Booking ID {booking.id}).")

            dispute.status = NoShowDispute.RESOLVED
            dispute.resolution_notes = "Auto-resolved: Client no-show confirmed. No client contest or admin action within 3 business days. Session considered complete for expert payment."
            dispute.resolved_at = timezone.now()
            dispute.resolved_by_system = True 
            dispute.save()

            # Mark booking complete, earnings will be PENDING
            self._mark_booking_complete_logic(
                booking, 
                "Auto-completed: Client no-show confirmed by system after 3 business days.",
                consultation_status_override=Consultation.CLIENT_NOSHOW
            )
            noshow_completed_count += 1
        self.stdout.write(f"Auto-resolved {noshow_completed_count} expert-reported client no-shows. Earnings set to PENDING.")


    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f"Starting automatic processing at {timezone.now()}..."))
        try:
            self.handle_auto_completion()
            self.stdout.write("---") 
            self.handle_dispute_resolution()
        except Exception as e:
            logger.error(f"Critical error during automatic processing: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"A critical error occurred during processing: {e}"))
        self.stdout.write(self.style.SUCCESS(f"Automatic processing finished at {timezone.now()}."))