# expert_marketplace/tasks.py
from django.utils import timezone
import stripe
from django.conf import settings
from .models import Booking
from django.core.mail import send_mail

def process_booking_auto_complete(booking_id):
    """
    Process a single booking for auto-completion after 24 hours
    """
    try:
        booking = Booking.objects.get(id=booking_id)

        # Check if booking is still in completed_by_expert status and not completed by user
        if booking.status == 'completed_by_expert' and booking.expert_completed and not booking.user_completed:
            # Auto-complete the booking
            booking.user_completed = True
            booking.user_completed_at = timezone.now()
            booking.status = 'completed'
            booking.save()

            # Process payout to expert
            stripe.api_key = settings.STRIPE_SECRET_KEY

            # Calculate platform fee (20%)
            total_amount = booking.payment_amount
            platform_fee = total_amount * 0.20
            expert_amount = total_amount - platform_fee

            # Create transfer to expert's connected account
            transfer = stripe.Transfer.create(
                amount=int(expert_amount * 100),  # Convert to cents
                currency='gbp',
                destination=booking.service.expert.stripe_account_id,
                transfer_group=f'booking_{booking.id}'
            )

            # Update booking with payout information
            booking.payout_processed = True
            booking.payout_processed_at = timezone.now()
            booking.save()

            # Send notification emails
            send_mail(
                'Session Payment Processed',
                f'The payment for your session has been automatically processed as no action was taken within 24 hours.',
                settings.DEFAULT_FROM_EMAIL,
                [booking.service.expert.user.email],
            )

            send_mail(
                'Session Marked as Complete',
                f'Your session has been automatically marked as complete as no action was taken within 24 hours.',
                settings.DEFAULT_FROM_EMAIL,
                [booking.user.email],
            )

            print(f"Successfully processed booking {booking_id}")
            return True

    except Booking.DoesNotExist:
        print(f"Booking {booking_id} not found")
    except Exception as e:
        print(f"Error processing booking {booking_id}: {str(e)}")
    return False