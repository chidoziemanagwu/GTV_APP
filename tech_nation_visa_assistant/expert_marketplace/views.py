# expert_marketplace/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
import json
import stripe
# from .email_service import send_noshow_dispute_emails # Assuming this is defined elsewhere or handled
from .models import Booking, Expert, Consultation, ExpertBonus, ExpertEarning, NoShowDispute # ADDED AvailabilitySlot
from .forms import (
    ConsultationBookingForm, 
    ExpertLoginForm, 
    ExpertProfileUpdateForm, 
    ExpertPasswordChangeForm, 
    ExpertAvailabilityJSONForm, # CHANGED from ExpertAvailabilityForm to AvailabilitySlotForm
)
from .assignment_engine import SmartAssignmentEngine
from .stripe_service import StripePaymentService, process_expert_payouts, process_refund as process_stripe_refund
from django.db.models import F
from datetime import date, datetime, timedelta, time
from django.utils.html import strip_tags
from django.core.mail import send_mail, BadHeaderError
from decimal import Decimal, InvalidOperation
import logging
from django.urls import reverse
from django.template.loader import render_to_string, TemplateDoesNotExist
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.db.models import Sum, Q
from operator import attrgetter # For sorting
from itertools import groupby # For grouping payout history
from django.db.models import Prefetch

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


@login_required
def book_consultation(request):
    if request.method == 'POST':
        form = ConsultationBookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            
            if request.user.is_authenticated:
                booking.user = request.user
            
            booking.consultation_fee = Decimal('100.00') # Or from settings/form
            booking.duration_minutes = 60 # Or from settings/form
            booking.status = 'pending_assignment' # Initial status
            # Save once to get an ID for the booking, which might be used by the engine or logs
            booking.save() 
            
            logger.info(f"Booking {booking.id} created with status 'pending_assignment'. Attempting to assign expert.")
            engine = SmartAssignmentEngine()
            # The assign_expert method returns the expert object if found, or None
            assigned_expert_object, error_message = engine.assign_expert(booking) 
            
            if assigned_expert_object:
                logger.info(f"Expert {assigned_expert_object.full_name} (ID: {assigned_expert_object.id}) found by engine for booking {booking.id}.")
                booking.expert = assigned_expert_object
                booking.status = 'pending_payment'
                booking.assigned_at = timezone.now()
                booking.save(update_fields=['expert', 'status', 'assigned_at']) 
                logger.info(f"Booking {booking.id} updated with expert {booking.expert.id} and status 'pending_payment'. Redirecting to payment.")
                
                return redirect('expert_marketplace:payment', booking_id=booking.id)
            else:
                logger.warning(f"No expert found for booking {booking.id}. Reason: {error_message}")
                booking.status = 'cancelled'
                booking.cancellation_reason = error_message or "No expert available for your request at this time."
                booking.save(update_fields=['status', 'cancellation_reason']) 
                
                messages.error(request, f"Sorry, we couldn't find an expert for your request: {error_message}")
                return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
        else:
            logger.error(f"Consultation booking form errors: {form.errors.as_json()}")
            
    form = ConsultationBookingForm() 

    consultants = Expert.objects.filter(is_active=True) 
    available_slots = get_available_time_slots() 

    return render(request, 'expert_marketplace/book_consultation.html', {
        'form': form,
        'consultation_fee': '100', 
        'consultation_duration': '60', 
        'experts': consultants,
        'available_slots': available_slots,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    })

def generate_meeting_link(booking_id):
    room_name = f"consultation-{booking_id}"
    return f"https://meet.jit.si/{room_name}"


@login_required
@require_POST
def expert_cancel_and_reassign_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    try:
        expert_profile = request.user.expert_profile
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "You must be an expert to perform this action.")
        logger.warning(f"User {request.user.id} attempted expert_cancel_and_reassign for booking {booking_id} without an expert profile.")
        return redirect('expert_marketplace:expert_login')

    # Ensure the booking actually has an expert assigned before trying to compare
    if not booking.expert:
        messages.error(request, "This booking does not currently have an expert assigned to it.")
        logger.warning(f"Attempt to cancel booking {booking_id} which has no expert assigned. Current expert_profile: {expert_profile.id if expert_profile else 'None'}")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    if booking.expert.id != expert_profile.id: # Compare IDs for safety
        messages.error(request, "You are not the assigned expert for this booking.")
        logger.warning(f"Expert {expert_profile.id} ({expert_profile.full_name}) tried to cancel booking {booking_id} assigned to expert {booking.expert.id} ({booking.expert.full_name}).")
        return redirect('expert_marketplace:expert_dashboard')

    if booking.status != 'confirmed':
        messages.error(request, f"This booking (status: {booking.get_status_display()}) cannot be cancelled by you as it's not 'confirmed'.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    original_expert_id = expert_profile.id
    original_expert_name = expert_profile.full_name
    cancellation_reason_by_expert = request.POST.get('cancellation_reason_by_expert', f"Cancelled by expert {original_expert_name} for reassignment.")
    
    logger.info(
        f"Expert {original_expert_name} (ID: {original_expert_id}, Type: {type(original_expert_id)}) "
        f"is attempting to cancel confirmed booking {booking.id} for reassignment."
    )

    booking.expert = None
    booking.status = 'pending_assignment' 
    booking.cancellation_reason = f"Original expert ({original_expert_name}) cancelled. Reason: {cancellation_reason_by_expert}. Attempting reassignment."
    booking.save(update_fields=['expert', 'status', 'cancellation_reason'])

    engine = SmartAssignmentEngine()
    
    logger.info(
        f"Calling assign_expert for booking {booking.id}. "
        f"Expert to exclude ID: {original_expert_id} (Type: {type(original_expert_id)})"
    )
    new_expert_obj, error_msg = engine.assign_expert(booking, expert_to_exclude_id=original_expert_id) 

    if new_expert_obj:
        booking.expert = new_expert_obj
        booking.status = 'confirmed'
        booking.assigned_at = timezone.now()
        booking.save(update_fields=['expert', 'status', 'assigned_at'])
        
        logger.info(f"Booking {booking.id} reassigned to {new_expert_obj.full_name} (ID: {new_expert_obj.id}) after {original_expert_name} cancelled.")
        messages.success(request, f"You have cancelled your participation. The booking has been successfully reassigned to {new_expert_obj.full_name}.")
        
        send_assignment_emails(booking)

        return redirect('expert_marketplace:expert_dashboard')
    else:
        logger.warning(f"Expert ({original_expert_name}) cancelled booking {booking.id}. Reassignment (excluding original expert ID: {original_expert_id}) failed. Error: {error_msg}. Proceeding to full refund.")
        
        booking.status = 'cancelled'
        booking.cancelled_at = timezone.now()
        booking.cancellation_reason = f"Original expert ({original_expert_name}) cancelled. No immediate replacement (excluding original expert ID: {original_expert_id}) for the slot was found. {error_msg or ''}"
        
        if booking.stripe_charge_id or booking.stripe_payment_intent_id:
            logger.info(f"Processing full refund for booking {booking.id} due to expert cancellation and no reassignment.")
            success, refund_details_or_error = process_stripe_refund(
                booking=booking,
                amount_decimal=booking.consultation_fee, 
                reason=f"Expert ({original_expert_name}) cancelled booking #{booking.id}, no immediate reassignment (excluding original expert ID: {original_expert_id})."
            )
            if success:
                send_cancellation_emails(booking) 
                messages.success(request, f"Your cancellation is processed. Booking ID {booking.id} cancelled. The client will receive a full refund of {booking.currency} {booking.refund_amount:.2f}.")
            else:
                logger.error(f"Stripe refund FAILED for booking {booking.id} after expert cancellation. Error: {refund_details_or_error}")
                messages.error(request, f"Cancellation processed, but Stripe refund FAILED: {refund_details_or_error}. Please check Stripe dashboard. Booking ID {booking.id} is marked as cancelled.")
        else:
            send_cancellation_emails(booking)
            messages.success(request, f"Your cancellation is processed. Booking ID {booking.id} cancelled (no payment was recorded to refund).")
        
        booking.save() 
        return redirect('expert_marketplace:expert_dashboard')




def payment_page(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    if not booking.expert:
        messages.error(request, "No expert has been assigned to this booking.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
        
    # MODIFIED LINE: Rely on 'pending_payment' as the primary status for payment.
    if booking.status != 'pending_payment': 
        if booking.status in ['confirmed', 'completed']:
            messages.info(request, "This booking has already been paid for.")
        else:
            messages.warning(request, f"This booking (status: {booking.get_status_display()}) is not currently awaiting payment.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    context = {
        'booking': booking,
        'expert': booking.expert,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, 'expert_marketplace/payment.html', context)


@require_POST
def create_payment_intent(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    if not booking.expert:
        return JsonResponse({'success': False, 'error': 'No expert assigned to this booking'})
    
    try:
        data = json.loads(request.body)
        payment_method_id = data.get('payment_method_id')
        
        if not payment_method_id:
            return JsonResponse({'success': False, 'error': 'Payment method ID is required'})
        
        intent = stripe.PaymentIntent.create(
            amount=int(booking.consultation_fee * 100),
            currency='gbp',
            payment_method=payment_method_id,
            confirmation_method='manual',
            confirm=True,
            metadata={
                'booking_id': str(booking.id),
                'client_email': booking.email,
                'client_name': booking.name,
                'expert_id': str(booking.expert.id)
            },
            return_url=request.build_absolute_uri(reverse('expert_marketplace:booking_detail', args=[booking.id])), # Use reverse
        )
        
        booking.stripe_payment_intent_id = intent.id
        booking.save()
        
        if intent.status == 'requires_action':
            return JsonResponse({
                'requires_action': True,
                'payment_intent_client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            })
        elif intent.status == 'succeeded':
            booking.status = 'confirmed'
            booking.stripe_charge_id = intent.latest_charge
            booking.save()
            
            send_confirmation_emails(booking) # CHANGED from send_assignment_emails
            
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('expert_marketplace:booking_detail', args=[booking.id]) # Use reverse
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Payment failed with status: {intent.status}'
            })
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error in create_payment_intent for booking {booking_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})
    except Exception as e:
        logger.error(f"Generic error in create_payment_intent for booking {booking_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})


@require_POST
def confirm_payment(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    if not booking.expert:
        return JsonResponse({'success': False, 'error': 'No expert assigned to this booking'})
    
    try:
        data = json.loads(request.body)
        payment_intent_id = data.get('payment_intent_id')
        
        if not payment_intent_id:
            return JsonResponse({'success': False, 'error': 'Payment intent ID is required'})
        
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if intent.status == 'succeeded':
            booking.status = 'confirmed'
            booking.stripe_charge_id = intent.latest_charge
            booking.save()
            
            send_confirmation_emails(booking) # CHANGED from send_assignment_emails
            
            return JsonResponse({
                'success': True,
                'redirect_url': reverse('expert_marketplace:booking_detail', args=[booking.id]) # Use reverse
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'Payment failed with status: {intent.status}'
            })
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error in confirm_payment for booking {booking_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)})
    except Exception as e:
        logger.error(f"Generic error in confirm_payment for booking {booking_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)})
    

@require_POST
def expert_respond(request, booking_id):
    """Expert accepts or declines booking"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Ensure expert_response_deadline is a datetime object for comparison
    if isinstance(booking.expert_response_deadline, (datetime, date)): # Assuming it's date or datetime
        # If it's just a date, combine with max time to make it end of day
        deadline_datetime = booking.expert_response_deadline
        if isinstance(deadline_datetime, date) and not isinstance(deadline_datetime, datetime):
            deadline_datetime = datetime.combine(deadline_datetime, time.max)
        
        # Make it timezone-aware if it's naive, assuming settings.TIME_ZONE
        if timezone.is_naive(deadline_datetime):
            deadline_datetime = timezone.make_aware(deadline_datetime)

        if timezone.now() > deadline_datetime:
            messages.error(request, 'Response deadline has passed.')
            return JsonResponse({'success': False, 'error': 'Response deadline passed'})
    else:
        logger.warning(f"Booking {booking.id} expert_response_deadline is not a valid date/datetime: {booking.expert_response_deadline}")
        # Decide how to handle this - perhaps allow response or show error. For now, let's allow.

    action = request.POST.get('action')
    
    if action == 'accept':
        booking.status = 'confirmed'
        booking.save()
        
        send_confirmation_emails(booking) # Assumes this sends to client and confirms expert
        messages.success(request, 'Booking confirmed and client notified.')
        return JsonResponse({'success': True, 'message': 'Booking confirmed'})
        
    elif action == 'decline':
        reason = request.POST.get('reason', 'Expert declined')
        
        previous_expert_name = booking.expert.get_full_name() if booking.expert else "Previous Expert"
        booking.expert = None
        booking.status = 'pending_assignment' 
        booking.cancellation_reason = f"{previous_expert_name} declined. Reason: {reason}. Attempting reassignment."
        booking.save()
        
        engine = SmartAssignmentEngine()
        new_expert, error_msg = engine.assign_expert(booking) # assign_expert should return (expert_obj, error_message_string)
        
        if new_expert:
            # booking.expert is set by assign_expert, status might also be updated by it (e.g. to 'pending_payment' or 'confirmed')
            # Ensure assign_expert updates booking.status appropriately or do it here.
            # If assign_expert sets it to 'pending_payment', payment flow might need to be re-triggered.
            # For now, assume assign_expert handles status and saves booking.
            send_assignment_emails(booking) # Send to new expert and client
            messages.info(request, f'Booking reassigned to {booking.expert.get_full_name() if booking.expert else "another expert"}.')
            return JsonResponse({'success': True, 'message': f'Reassigned to {booking.expert.get_full_name() if booking.expert else "another expert"}.'})
        else:
            # No more experts - cancel booking and refund
            booking.status = 'cancelled'
            booking.cancellation_reason = f"{previous_expert_name} declined. No alternative expert available. {error_msg or ''}"
            booking.cancelled_by = 'system' # Or 'expert_decline_final'
            booking.cancelled_at = timezone.now()
            
            if booking.stripe_charge_id or booking.stripe_payment_intent_id:
                logger.info(f"Processing full refund for booking {booking.id} due to expert decline and no reassignment.")
                success, refund_details_or_error = process_stripe_refund(
                    booking=booking,
                    amount_decimal=booking.consultation_fee, # Full refund
                    reason=f"Expert declined booking #{booking.id}, no reassignment. Original reason: {reason}"
                )
                if success:
                    # booking.refund_amount and status are updated by the service
                    send_refund_email(booking, booking.refund_amount) # Pass the amount from the booking model
                    messages.success(request, f"Booking cancelled as no alternative expert found. Full refund of £{booking.refund_amount:.2f} processed.")
                else:
                    logger.error(f"Stripe refund FAILED for booking {booking.id} after expert decline (no reassignment). Error: {refund_details_or_error}")
                    messages.error(request, f"Booking cancelled, but Stripe refund FAILED: {refund_details_or_error}. Please check Stripe dashboard.")
                    # Booking status is already 'cancelled', but refund failed.
            else:
                messages.success(request, "Booking cancelled as no alternative expert found (no payment to refund).")
            
            booking.save() # Save final cancellation details
            return JsonResponse({'success': True, 'message': 'No experts available, booking cancelled and refunded if applicable.'})
    
    return JsonResponse({'success': False, 'error': 'Invalid action'})


def get_available_time_slots():
    """Get available booking slots"""
    slots = []
    today = timezone.now().date()
    
    for i in range(14):  # Next 14 days
        current_date = today + timedelta(days=i)
        
        # Skip weekends
        if current_date.weekday() >= 5:
            continue
        
        # Add slots from 10 AM to 5 PM
        for hour in range(10, 17):  # 10 AM to 4 PM (last slot starts at 4 PM)
            slot_time = time(hour, 0)
            
            # Check expert availability
            available_count = Expert.objects.filter(
                is_active=True
            ).exclude(
                bookings__scheduled_date=current_date,
                bookings__scheduled_time=slot_time,
                bookings__status__in=['confirmed', 'pending_payment', 'awaiting_assignment', 'pending_assignment']
            ).count()
            
            if available_count > 0:
                slots.append({
                    'date': current_date.isoformat(),
                    'time': slot_time.strftime('%H:%M'),
                    'available_experts': available_count
                })
    
    return slots

def send_confirmation_emails(booking):
    """Send confirmation emails with meeting link"""
    # Generate meeting link if not already set
    if not booking.meeting_link:
        booking.meeting_link = generate_meeting_link(booking.id)
        booking.save()
    
    # Client email
    client_context = {
        'booking': booking,
        'expert': booking.expert,
        'site_url': settings.SITE_URL,
        'meeting_link': booking.meeting_link,
        'duration': booking.duration_minutes or 60,
        'expertise': booking.expertise_needed or "General Consultation",
    }
    
    client_html = render_to_string('emails/expert/booking_confirmed_client.html', client_context)
    client_text = strip_tags(client_html)
    
    # Make sure we're using the client's email from the booking
    client_email_address = booking.email
    if not client_email_address or '@' not in client_email_address:
        # Fallback to user email if available
        client_email_address = booking.user.email if booking.user else settings.DEFAULT_FROM_EMAIL
    
    client_email = EmailMultiAlternatives(
        f'Consultation Confirmed with {booking.expert.first_name}',
        client_text,
        settings.DEFAULT_FROM_EMAIL,
        [client_email_address],
    )
    client_email.attach_alternative(client_html, "text/html")
    client_email.send()
    
    # Expert email
    if booking.expert and booking.expert.email and '@' in booking.expert.email:
        expert_context = {
            'booking': booking,
            'client_name': booking.name,
            'consultation_url': f"{settings.SITE_URL}/consultation/booking/{booking.id}/",
            'meeting_link': booking.meeting_link,
            'duration': booking.duration_minutes or 60,
            'expertise': booking.expertise_needed or "General Consultation",
        }
        
        expert_html = render_to_string('emails/expert/booking_confirmed_expert.html', expert_context)
        expert_text = strip_tags(expert_html)
        
        expert_email = EmailMultiAlternatives(
            f'Consultation Confirmed with {booking.name}',
            expert_text,
            settings.DEFAULT_FROM_EMAIL,
            [booking.expert.email],
        )
        expert_email.attach_alternative(expert_html, "text/html")
        expert_email.send()
    else:
        print("Expert email not sent - no valid expert email address") 





def send_assignment_emails(booking):
    """Send emails to client and expert"""
    # Generate meeting link if not already set
    if not booking.meeting_link:
        booking.meeting_link = generate_meeting_link(booking.id)
        booking.save()
    
    # Client email
    client_context = {
        'booking': booking,
        'expert': booking.expert,
        'site_url': settings.SITE_URL,
        'meeting_link': booking.meeting_link,
        'duration': booking.duration_minutes or 60,
        'expertise': booking.expertise_needed or "General Consultation",
    }
    
    client_html = render_to_string('emails/expert/booking_confirmed_client.html', client_context)
    client_text = strip_tags(client_html)
    
    # Make sure we're using the client's email from the booking
    client_email_address = booking.email
    if not client_email_address or '@' not in client_email_address:
        # Fallback to user email if available
        client_email_address = booking.user.email if booking.user else settings.DEFAULT_FROM_EMAIL
    
    client_email = EmailMultiAlternatives(
        f'Expert Assigned: {booking.expert.first_name} for your consultation',
        client_text,
        settings.DEFAULT_FROM_EMAIL,
        [client_email_address],
    )
    client_email.attach_alternative(client_html, "text/html")
    client_email.send()
    
    # Expert email
    if booking.expert and booking.expert.email and '@' in booking.expert.email:
        expert_context = {
            'booking': booking,
            'client_name': booking.name,
            'response_url': f"{settings.SITE_URL}/expert/respond/{booking.id}/",
            'deadline': booking.expert_response_deadline,
            'earnings': booking.expert_earnings,
            'meeting_link': booking.meeting_link,
            'consultation_url': f"{settings.SITE_URL}/consultation/booking/{booking.id}/",
            'duration': booking.duration_minutes or 60,
            'expertise': booking.expertise_needed or "General Consultation",
        }
        
        expert_html = render_to_string('emails/expert/booking_confirmed_expert.html', expert_context)
        expert_text = strip_tags(expert_html)
        
        expert_email = EmailMultiAlternatives(
            f'New Consultation Assignment',
            expert_text,
            settings.DEFAULT_FROM_EMAIL,
            [booking.expert.email],
        )
        expert_email.attach_alternative(expert_html, "text/html")
        expert_email.send()
    else:
        print("Expert email not sent - no valid expert email address")



def send_refund_email(booking, refund_amount):
    """Send refund confirmation email to both client and expert"""
    context = {
        'booking': booking,
        'refund_amount': refund_amount,
        'site_name': 'Your Site Name'  # Replace with your actual site name
    }
    
    try:
        # Send email to client
        client_subject = f"Refund Confirmation for Booking #{booking.id}"
        client_message = render_to_string('emails/client/refund_confirmation.html', context)
        send_mail(
            client_subject,
            strip_tags(client_message),
            settings.DEFAULT_FROM_EMAIL,
            [booking.email],
            html_message=client_message,
            fail_silently=True,
        )
        
        # Send email to expert if assigned
        if booking.expert:
            expert_subject = f"Booking Cancellation: #{booking.id}"
            expert_message = render_to_string('emails/expert/refund_confirmation.html', context)
            send_mail(
                expert_subject,
                strip_tags(expert_message),
                settings.DEFAULT_FROM_EMAIL,
                [booking.expert.email],
                html_message=expert_message,
                fail_silently=True,
            )
    except Exception as e:
        # Log the error but don't stop the payment process
        print(f"Email sending error: {str(e)}")

def booking_status(request, booking_id):
    """Show booking status"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    context = {'booking': booking}
    return render(request, 'expert_marketplace/booking_status.html', context)

def booking_confirmation(request, booking_id):
    """Show booking confirmation after successful payment"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Redirect to booking status if already processed
    if booking.status not in ['pending_payment', 'paid', 'awaiting_assignment', 'confirmed', 'pending_assignment']:
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
    
    # Safely handle the case where booking.expert might be None
    expert = booking.expert if hasattr(booking, 'expert') and booking.expert is not None else None
    
    context = {
        'booking': booking,
        'expert': expert,
        'consultation_fee': booking.consultation_fee,
        'scheduled_datetime': datetime.combine(booking.scheduled_date, booking.scheduled_time),
        'duration': booking.duration_minutes,
    }
    
    return render(request, 'expert_marketplace/booking_confirmation.html', context)

@login_required
def booking_detail(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    user_has_expert_profile = hasattr(request.user, 'expert_profile')
    viewer_is_booking_client = (booking.user == request.user)
    viewer_is_booking_expert = False
    if user_has_expert_profile and booking.expert and booking.expert == request.user.expert_profile:
        viewer_is_booking_expert = True
    viewer_is_staff = request.user.is_staff

    if not (viewer_is_staff or viewer_is_booking_client or viewer_is_booking_expert):
        messages.error(request, "You don't have permission to view this booking.")
        if user_has_expert_profile:
            return redirect('expert_marketplace:expert_dashboard')
        else:
            # Assuming 'dashboard' is your client-side dashboard URL name
            return redirect('dashboard') 

    # --- Fetch Dispute Record if applicable ---
    dispute_record = None
    if booking.status == 'dispute':
        try:
            # A booking might have multiple dispute entries if a system allows re-opening,
            # so fetch the latest one based on reported_at.
            # If your logic ensures only one active dispute, .get() or .first() is fine.
            dispute_record = NoShowDispute.objects.filter(booking=booking).order_by('-reported_at').first()
            if not dispute_record:
                logger.warning(f"Booking {booking.id} has status 'dispute' but no NoShowDispute record found.")
        except Exception as e:
            logger.error(f"Error fetching dispute record for booking {booking.id}: {e}")
            # dispute_record remains None

    context = {
        'booking': booking,
        'is_expert': viewer_is_booking_expert, 
        'is_client': viewer_is_booking_client, 
        'is_staff': viewer_is_staff,
        'dispute_record': dispute_record, # Add dispute_record to context
    }
    
    if viewer_is_booking_expert:
        template_name = 'expert_marketplace/booking_detail_expert_wrapper.html'
    else:
        template_name = 'expert_marketplace/booking_detail_client_wrapper.html'
        
    return render(request, template_name, context)









def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    cancelling_party = 'client' # Or determine dynamically
    cancellation_reason_input = request.POST.get('cancellation_reason', f'Cancelled by {cancelling_party}.')

    if booking.status == 'cancelled':
        messages.info(request, "This booking has already been cancelled.")
        # Ensure this redirect works, or use a known good one like a dashboard.
        return redirect('expert_marketplace:client_bookings') # Example of a namespaced redirect

    actual_refund_amount = booking.refund_amount or Decimal('0.00') # Start with existing refund amount
    refund_message_suffix = ""

    if booking.stripe_payment_intent_id and booking.consultation_fee > Decimal('0.00'):
        try:
            # Check if Stripe already thinks it's refunded before trying to refund again
            payment_intent = stripe.PaymentIntent.retrieve(booking.stripe_payment_intent_id, expand=['latest_charge'])
            charge = payment_intent.latest_charge

            if charge.refunded:
                messages.info(request, f"This charge (ID: {charge.id}) was already marked as fully refunded by Stripe.")
                # If Stripe says it's refunded, trust it and update your records if they don't match.
                # You might want to fetch the refund objects associated with the charge to get the amount.
                actual_refund_amount = booking.consultation_fee # Assuming full refund if charge.refunded is true
                                                            # Or, if you have partial refund IDs, sum them.
                                                            # For 50% policy, this might need adjustment.
                if booking.refund_amount != (booking.consultation_fee * Decimal('0.50')):
                     # If your policy is 50% and Stripe says fully refunded, there's a mismatch to investigate.
                     # For now, let's assume we want to record the 50% if that's the policy.
                     actual_refund_amount = (booking.consultation_fee * Decimal('0.50')).quantize(Decimal('0.01'))

                refund_message_suffix = " (Stripe indicated it was already refunded)."
            
            elif charge.amount_refunded > 0 and charge.amount_refunded < charge.amount:
                 messages.info(request, f"This charge (ID: {charge.id}) was already partially refunded by Stripe.")
                 # Your 50% policy might mean this is already done.
                 # Let's assume if it's partially refunded, it matches your 50% policy.
                 actual_refund_amount = Decimal(charge.amount_refunded) / 100
                 refund_message_suffix = " (Stripe indicated it was already partially refunded)."

            else: # Not fully or partially refunded yet, so attempt our 50% refund
                refund_amount_to_process = (booking.consultation_fee * Decimal('0.50')).quantize(Decimal('0.01'))
                if refund_amount_to_process > Decimal('0.00'):
                    stripe_refund_amount_cents = int(refund_amount_to_process * 100)
                    refund = stripe.Refund.create(
                        charge=charge.id, # Refund the specific charge
                        amount=stripe_refund_amount_cents,
                        reason='requested_by_customer',
                        metadata={
                            'booking_id': str(booking.id),
                            'refund_policy': '50_percent_on_cancellation',
                            'cancelled_by': cancelling_party
                        }
                    )
                    booking.stripe_refund_id = refund.id
                    booking.refund_processed_at = timezone.now()
                    actual_refund_amount = refund_amount_to_process
                    messages.success(request, f"A 50% refund of {booking.currency} {actual_refund_amount:.2f} has been processed.")
                else:
                    messages.info(request, "No refund amount was applicable based on the consultation fee.")
        
        except stripe.error.InvalidRequestError as e_stripe:
            if "has already been refunded" in str(e_stripe).lower():
                messages.warning(request, f"Stripe indicated the charge was already refunded. Updating records accordingly. {str(e_stripe)}")
                # If it's already refunded, we assume it was for the correct 50% amount as per policy.
                # Or you might want to fetch the actual refund amount from Stripe here.
                actual_refund_amount = (booking.consultation_fee * Decimal('0.50')).quantize(Decimal('0.01'))
                refund_message_suffix = " (Stripe confirmed it was already refunded)."
            else:
                messages.error(request, f"Stripe refund failed: {str(e_stripe)}. Please contact support.")
                return redirect('expert_marketplace:booking_detail', booking_id=booking.id) # Use namespaced redirect
        except stripe.error.StripeError as e_stripe:
            messages.error(request, f"Stripe operation failed: {str(e_stripe)}. Please contact support.")
            return redirect('expert_marketplace:booking_detail', booking_id=booking.id) # Use namespaced redirect
        except Exception as e_general:
            messages.error(request, f"An unexpected error occurred during refund: {str(e_general)}.")
            return redirect('expert_marketplace:booking_detail', booking_id=booking.id) # Use namespaced redirect

    # Proceed to cancel the booking in your system
    booking.status = 'cancelled'
    booking.cancelled_at = timezone.now()
    booking.cancellation_reason = cancellation_reason_input
    booking.cancelled_by = cancelling_party
    booking.refund_amount = actual_refund_amount
    
    fields_to_update = ['status', 'cancelled_at', 'cancellation_reason', 'cancelled_by', 'refund_amount']
    if hasattr(booking, 'stripe_refund_id') and booking.stripe_refund_id: # Only add if set
         fields_to_update.append('stripe_refund_id')
    if hasattr(booking, 'refund_processed_at') and booking.refund_processed_at: # Only add if set
         fields_to_update.append('refund_processed_at')
    booking.save(update_fields=fields_to_update)

    # Update ExpertEarning
    try:
        earning_record = ExpertEarning.objects.get(booking=booking)
        if earning_record.status != ExpertEarning.CANCELLED:
            # ... (your logic to adjust Expert.pending_payout) ...
            earning_record.status = ExpertEarning.CANCELLED
            earning_record.amount = Decimal('0.00')
            earning_record.notes = (
                f"Booking ID {booking.id} cancelled by {booking.cancelled_by}. "
                f"Client refund: {booking.currency} {actual_refund_amount:.2f}{refund_message_suffix}. Earning voided."
            )
            earning_record.save(update_fields=['status', 'amount', 'notes'])
    except ExpertEarning.DoesNotExist:
        pass
    except Exception as e_earning:
        messages.warning(request, f"Booking cancelled, but issue updating earning records: {str(e_earning)}")

    if not booking.stripe_payment_intent_id:
        messages.info(request, "Booking cancelled. No online payment was recorded.")
    else:
        messages.success(request, f"Booking cancelled. Refund amount: {booking.currency} {actual_refund_amount:.2f}{refund_message_suffix}.")
    
    return redirect('expert_marketplace:client_bookings') # Redirect to a list view or dashboard




def my_bookings(request):
    """Show all bookings for the current user"""
    if not request.user.is_authenticated:
        messages.error(request, "You need to be logged in to view your bookings.")
        return redirect('login')
    
    # Check if user is an expert
    is_expert = hasattr(request.user, 'expert_profile')
    
    if is_expert:
        # Get bookings where user is the expert
        bookings = Booking.objects.filter(expert__user=request.user).order_by('-created_at')
    else:
        # Get bookings where user is the client
        bookings = Booking.objects.filter(user=request.user).order_by('-created_at')
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        bookings = bookings.filter(status=status_filter)
    
    context = {
        'bookings': bookings,
        'is_expert': is_expert,
        'status_filter': status_filter or 'all',
        'statuses': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'expert_marketplace/my_bookings.html', context)

@csrf_exempt
def stripe_webhook(request):
    """Handle Stripe webhook events"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        
        # Handle the event
        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            handle_payment_success(payment_intent)
        elif event['type'] == 'payment_intent.payment_failed':
            payment_intent = event['data']['object']
            handle_payment_failure(payment_intent)
        elif event['type'] == 'charge.refunded':
            charge = event['data']['object']
            handle_refund(charge)
        
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def mark_consultation_complete(request, booking_id):
    """Mark a consultation as complete (admin or expert only)"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check permissions
    if not request.user.is_staff and (not hasattr(booking, 'expert') or booking.expert.user != request.user):
        messages.error(request, "You don't have permission to complete this consultation.")
        return redirect('dashboard')
    
    # Check if booking can be marked as complete
    if booking.status != 'confirmed':
        messages.error(request, "This booking cannot be marked as complete.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
    
    if request.method == 'POST':
        notes = request.POST.get('completion_notes', '')
        
        # Update booking status
        booking.status = 'completed'
        booking.completed_at = timezone.now()
        booking.completion_notes = notes
        booking.save()
        
        # Create consultation record if it doesn't exist
        consultation, created = Consultation.objects.get_or_create(
            booking=booking,
            defaults={
                'expert': booking.expert,
                'client': booking.user,
                'status': 'completed',
                'notes': notes
            }
        )
        
        if not created:
            consultation.status = 'completed'
            consultation.notes = notes
            consultation.save()
        
        # Process expert payment
        try:
            earning, created = ExpertEarning.objects.get_or_create(
                expert=booking.expert,
                booking=booking,
                defaults={
                    'amount': booking.expert_earnings,
                    'status': 'pending'
                }
            )
            
            if not created:
                earning.status = 'pending'
                earning.save()
        except Exception as e:
            messages.warning(request, f"Consultation marked as complete, but there was an issue with expert payment: {str(e)}")
        
        # Send completion emails
        send_completion_emails(booking)
        
        messages.success(request, "Consultation marked as complete successfully.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
    
    return render(request, 'expert_marketplace/mark_consultation_complete.html', {
        'booking': booking
    })

def handle_payment_success(payment_intent):
    """Handle successful payment webhook event"""
    booking_id = payment_intent.get('metadata', {}).get('booking_id')
    if not booking_id:
        return
    
    try:
        booking = Booking.objects.get(id=booking_id)
        
        # Update booking if not already processed
        if booking.status == 'pending_payment':
            booking.status = 'confirmed'  # Changed from 'awaiting_assignment'
            booking.stripe_charge_id = payment_intent.get('latest_charge', '')
            booking.save()
            
            # Expert should already be assigned, send confirmation emails
            if booking.expert:
                send_confirmation_emails(booking)
    except Booking.DoesNotExist:
        pass

def handle_payment_failure(payment_intent):
    """Handle failed payment webhook event"""
    booking_id = payment_intent.get('metadata', {}).get('booking_id')
    if not booking_id:
        return
    
    try:
        booking = Booking.objects.get(id=booking_id)
        booking.status = 'pending_payment'
        booking.save()
    except Booking.DoesNotExist:
        pass

def handle_refund(charge):
    """Handle refund webhook event"""
    # Find booking by charge ID
    try:
        booking = Booking.objects.get(stripe_charge_id=charge.id)
        
        # Check if this is a full refund
        if charge.refunded:
            booking.status = 'refunded'
            booking.refund_amount = booking.consultation_fee
            booking.save()
    except Booking.DoesNotExist:
        pass

def send_cancellation_emails(booking):
    """Send cancellation notification emails"""
    # Client email
    client_html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Your Consultation Booking Has Been Cancelled</title></head>
    <body style="margin: 0; padding: 0; background-color: #f9fafb;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr><td align="center" style="padding: 20px 0;">
            <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
              <tr><td style="background-color: #4f46e5; padding: 20px; text-align: center;"><h1 style="color: #ffffff; margin: 0; font-family: Arial, sans-serif;">Expert Consultation</h1></td></tr>
              <tr><td style="padding: 30px 20px;">
                  <h2 style="color: #1f2937; margin-top: 0; font-family: Arial, sans-serif;">Booking Cancellation Confirmation</h2>
                  <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">Hello {booking.name or (booking.user.get_full_name() if booking.user else 'Client')},</p>
                  <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">Your consultation booking (Reference #{booking.id}) has been cancelled.</p>
                  <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1f2937; font-family: Arial, sans-serif;">Booking Details</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Date:</strong> {booking.scheduled_date.strftime('%B %d, %Y') if booking.scheduled_date else 'N/A'}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Time:</strong> {booking.scheduled_time.strftime('%H:%M') if booking.scheduled_time else 'N/A'}</p>
                    {'<p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Expert:</strong> ' + booking.expert.full_name + '</p>' if booking.expert else ''}
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Expertise:</strong> {booking.get_expertise_needed_display() or "General Consultation"}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Duration:</strong> {booking.duration_minutes} minutes</p>
                  </div>
                  {f'''
                  <div style="background-color: #e0f2fe; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #0369a1; font-family: Arial, sans-serif;">Refund Information</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">A refund of <strong>£{booking.refund_amount:.2f}</strong> has been processed to your original payment method.</p>
                    {'<p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">This is a full refund as the cancellation was initiated by the expert or our system.</p>' if booking.cancelled_by == 'expert' or booking.cancelled_by == 'system' else '<p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">This is a partial refund in accordance with our cancellation policy.</p>'}
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">The refund should appear in your account within 5-10 business days, depending on your payment provider.</p>
                  </div>
                  ''' if booking.refund_amount and booking.refund_amount > 0 else ''}
                  <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">If you have any questions, please contact our support team.</p>
                  <div style="margin-top: 30px; text-align: center;"><a href="{settings.SITE_URL}/consultation/book/" style="background-color: #4f46e5; color: white; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-family: Arial, sans-serif; display: inline-block;">Book Another Consultation</a></div>
              </td></tr>
              <tr><td style="background-color: #f3f4f6; padding: 15px; text-align: center; font-family: Arial, sans-serif; font-size: 12px; color: #6b7280;"><p>&copy; {timezone.now().year} {getattr(settings, 'SITE_NAME', 'Expert Consultation')}. All rights reserved.</p><p>This is an automated email.</p></td></tr>
            </table>
        </td></tr>
      </table>
    </body></html>
    """
    
    client_email_obj = EmailMultiAlternatives(
        f'Your Consultation Booking Has Been Cancelled - {getattr(settings, "SITE_NAME", "Expert Consultation")}',
        f'Your consultation booking (ID: {booking.id}) has been cancelled. Refund amount: £{booking.refund_amount or 0:.2f}',
        settings.DEFAULT_FROM_EMAIL,
        [booking.email]
    )
    client_email_obj.attach_alternative(client_html, "text/html")
    try:
        client_email_obj.send(fail_silently=False)
        logger.info(f"Cancellation email sent to client {booking.email} for booking {booking.id}")
    except Exception as e:
        logger.error(f"Failed to send cancellation email to client {booking.email} for booking {booking.id}: {e}")

    # Expert email (if assigned)
    if booking.expert and booking.expert.email:
        expert_html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Consultation Booking Cancelled</title></head>
        <body style="margin: 0; padding: 0; background-color: #f9fafb;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr><td align="center" style="padding: 20px 0;">
                <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                  <tr><td style="background-color: #4f46e5; padding: 20px; text-align: center;"><h1 style="color: #ffffff; margin: 0; font-family: Arial, sans-serif;">Expert Consultation</h1></td></tr>
                  <tr><td style="padding: 30px 20px;">
                      <h2 style="color: #1f2937; margin-top: 0; font-family: Arial, sans-serif;">Booking Cancellation Notice</h2>
                      <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">Hello {booking.expert.first_name if booking.expert else 'Expert'},</p>
                      <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">A consultation booking (Reference #{booking.id}) has been cancelled by {'you' if booking.cancelled_by == 'expert' else ('the client' if booking.cancelled_by == 'client' else 'the system') }.</p>
                      <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #1f2937; font-family: Arial, sans-serif;">Booking Details</h3>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Client:</strong> {booking.name or (booking.user.get_full_name() if booking.user else 'N/A')}</p>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Date:</strong> {booking.scheduled_date.strftime('%B %d, %Y') if booking.scheduled_date else 'N/A'}</p>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Time:</strong> {booking.scheduled_time.strftime('%H:%M') if booking.scheduled_time else 'N/A'}</p>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Expertise:</strong> {booking.get_expertise_needed_display() or "General Consultation"}</p>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Duration:</strong> {booking.duration_minutes} minutes</p>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Cancellation Reason:</strong> {booking.cancellation_reason or "Not specified"}</p>
                      </div>
                      <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">This time slot is now available for other bookings.</p>
                      {f'''
                      <div style="background-color: #fef3c7; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #92400e; font-family: Arial, sans-serif;">Important Note</h3>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">Since this cancellation was initiated by you, the client has received a full refund.</p>
                        <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">Please remember that frequent cancellations may affect your expert rating and future assignments.</p>
                      </div>
                      ''' if booking.cancelled_by == 'expert' else ''}
                      <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">If you have any questions, please contact the admin team.</p>
                  </td></tr>
                  <tr><td style="background-color: #f3f4f6; padding: 15px; text-align: center; font-family: Arial, sans-serif; font-size: 12px; color: #6b7280;"><p>&copy; {timezone.now().year} {getattr(settings, 'SITE_NAME', 'Expert Consultation')}. All rights reserved.</p><p>This is an automated email.</p></td></tr>
                </table>
            </td></tr>
          </table>
        </body></html>
        """
        
        expert_email_obj = EmailMultiAlternatives(
            f'Consultation Booking Cancelled - {getattr(settings, "SITE_NAME", "Expert Consultation")}',
            f'A consultation booking (ID: {booking.id}) has been cancelled by {"you" if booking.cancelled_by == "expert" else ("the client" if booking.cancelled_by == "client" else "the system")}.',
            settings.DEFAULT_FROM_EMAIL,
            [booking.expert.email]
        )
        expert_email_obj.attach_alternative(expert_html, "text/html")
        try:
            expert_email_obj.send(fail_silently=False)
            logger.info(f"Cancellation email sent to expert {booking.expert.email} for booking {booking.id}")
        except Exception as e:
            logger.error(f"Failed to send cancellation email to expert {booking.expert.email} for booking {booking.id}: {e}")





def send_completion_emails(booking):
    """
    Sends consultation completion emails to both the client and the expert.
    """
    if not booking:
        logger.error("send_completion_emails called with no booking object.")
        return

    client = booking.user
    expert = booking.expert

    # Retrieve completion notes from the Consultation model
    try:
        consultation_record = Consultation.objects.get(booking=booking)
        completion_notes = consultation_record.notes
    except Consultation.DoesNotExist:
        completion_notes = "N/A" # Default if no consultation record or notes found
        logger.warning(f"No Consultation record found for booking {booking.id} when sending completion email.")
    except Exception as e:
        completion_notes = "Error retrieving notes."
        logger.error(f"Error retrieving notes for booking {booking.id}: {e}")


    site_name = getattr(settings, 'SITE_NAME', 'Our Platform')
    # Construct site_url carefully, ensuring it's the correct base URL
    # For local development, request.build_absolute_uri('/') might be useful if you have 'request'
    # but since this function might be called outside a request-response cycle, settings is safer.
    # Ensure SITE_URL is configured in your settings.py (e.g., 'http://127.0.0.1:8000')
    base_site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000') 
    
    try:
        booking_detail_path = reverse('expert_marketplace:booking_detail', args=[booking.id])
        booking_url = f"{base_site_url}{booking_detail_path}"
    except Exception as e:
        logger.error(f"Could not reverse URL for booking_detail for booking {booking.id}: {e}")
        booking_url = base_site_url # Fallback URL

    # --- Email to Client ---
    if client and client.email:
        client_subject = f"Your {booking.get_expertise_needed_display() or 'Consultation'} is Complete - {site_name}"
        client_context = {
            'user': client,  # The client User object
            'booking': booking,
            'expert_name': expert.user.get_full_name() if expert and expert.user else "Our Expert",
            'completion_notes': completion_notes,
            'site_name': site_name,
            'booking_url': booking_url, # Pass the fully qualified URL
        }
        try:
            client_html_message = render_to_string('emails/expert/consultation_completed_client.html', client_context)
            send_mail(
                client_subject,
                '', # Plain text message (optional, can be generated from HTML or be a simpler version)
                settings.DEFAULT_FROM_EMAIL,
                [client.email],
                html_message=client_html_message,
                fail_silently=False,
            )
            logger.info(f"Consultation completion email sent to client {client.email} for booking {booking.id}")
        except BadHeaderError:
            logger.error(f"Invalid header found while sending completion email to client for booking {booking.id}")
        except Exception as e:
            logger.error(f"Error sending consultation completion email to client {client.email} for booking {booking.id}: {e}")
    else:
        logger.warning(f"Client or client email missing for booking {booking.id}. Cannot send completion email to client.")

    # --- Email to Expert ---
    if expert and expert.user and expert.user.email:
        expert_subject = f"Consultation with '{client.get_full_name()}' Marked Complete - {site_name}"
        expert_context = {
            'expert_user': expert.user, # The expert User object
            'client_name': client.get_full_name() if client else "the client",
            'booking': booking,
            'completion_notes': completion_notes,
            'site_name': site_name,
            'booking_url': booking_url,
        }
        try:
            # You'll need to create this template: emails/expert/consultation_completed_expert.html
            expert_html_message = render_to_string('emails/expert/consultation_completed_expert.html', expert_context)
            send_mail(
                expert_subject,
                '', # Plain text message
                settings.DEFAULT_FROM_EMAIL,
                [expert.user.email],
                html_message=expert_html_message,
                fail_silently=False,
            )
            logger.info(f"Consultation completion email sent to expert {expert.user.email} for booking {booking.id}")
        except BadHeaderError:
            logger.error(f"Invalid header found while sending completion email to expert for booking {booking.id}")
        except Exception as e:
            # Check if it's a TemplateDoesNotExist error for the expert email
            if isinstance(e, TemplateDoesNotExist):
                 logger.error(f"Template for expert completion email not found: emails/expert/consultation_completed_expert.html. Booking ID: {booking.id}")
            else:
                logger.error(f"Error sending consultation completion email to expert {expert.user.email} for booking {booking.id}: {e}")
    else:
        logger.warning(f"Expert user or expert email missing for booking {booking.id}. Cannot send completion email to expert.")




@login_required
def client_bookings(request):
    # The @login_required decorator handles authentication.
    # Redirect experts to their own dashboard.
    if hasattr(request.user, 'expert_profile'):
        messages.info(request, "You are viewing the expert dashboard.")
        return redirect('expert_marketplace:expert_dashboard') # Or 'expert_marketplace:my_bookings'

    all_user_bookings = Booking.objects.filter(user=request.user)
    today = timezone.now().date()
    # now_time = timezone.now().time() # For more precise past/upcoming if needed for same-day bookings

    # Upcoming: Confirmed and scheduled for today or future
    upcoming_bookings = all_user_bookings.filter(
        status='confirmed',
        scheduled_date__gte=today
        # If you want to be more precise for today's bookings:
        # Q(status='confirmed', scheduled_date__gt=today) |
        # Q(status='confirmed', scheduled_date=today, scheduled_time__gte=now_time)
    ).order_by('scheduled_date', 'scheduled_time')

    # Pending: Awaiting payment or expert assignment
    pending_bookings = all_user_bookings.filter(
        status__in=['pending_payment', 'awaiting_assignment']
    ).order_by('-created_at')

    # Completed
    completed_bookings = all_user_bookings.filter(
        status='completed'
    ).order_by('-completed_at', '-scheduled_date', '-scheduled_time')

    # Cancelled (more comprehensive)
    # These are terminal states where the booking didn't proceed as a normal consultation.
    cancelled_statuses_list = [
        'cancelled',              # General cancellation
        'refunded',               # Full refund
        'partially_refunded',     # Partial refund
        'expert_noshow',          # Marked as expert no-show (often leads to refund/resolution)
        'client_noshow',          # Marked as client no-show
        # Add any other custom status that means the booking is effectively cancelled from client's perspective
    ]
    cancelled_bookings = all_user_bookings.filter(
        status__in=cancelled_statuses_list
    ).order_by('-cancelled_at', '-updated_at', '-scheduled_date') # Order by relevant dates

    # Past: Scheduled date is before today.
    # This will include bookings that are also in 'completed' or 'cancelled' lists if their date is past.
    # The template's "Past" tab can then show the specific status of these past bookings.
    past_bookings = all_user_bookings.filter(
        scheduled_date__lt=today
        # If you want to include today's bookings where time has passed:
        # Q(scheduled_date__lt=today) |
        # Q(scheduled_date=today, scheduled_time__lt=now_time)
    ).exclude( # Ensure truly upcoming bookings (today but future time) are not in "Past"
        status='confirmed', scheduled_date=today #, scheduled_time__gte=now_time
    ).order_by('-scheduled_date', '-scheduled_time')


    context = {
        'upcoming_bookings': upcoming_bookings,
        'pending_bookings': pending_bookings,
        'completed_bookings': completed_bookings,
        'cancelled_bookings': cancelled_bookings,
        'past_bookings': past_bookings,
        'statuses': Booking.STATUS_CHOICES, # For potential filter dropdowns
        'active_nav': 'my_consultations', # For base template navigation highlighting
    }
    return render(request, 'expert_marketplace/client_bookings.html', context)

# expert_marketplace/views.py (add these functions)

def send_noshow_dispute_emails(dispute):
    """Send emails to admin and expert about the dispute"""
    # Email to expert
    if dispute.expert_email:
        # Generate the correct path using reverse
        dispute_path = reverse('expert_marketplace:dispute_response', kwargs={'dispute_code': dispute.dispute_code})
        
        # Construct the full URL
        response_url = f"{settings.SITE_URL}{dispute_path}" # No extra slash needed if SITE_URL ends with / and dispute_path starts with /

        # It's good practice to ensure SITE_URL doesn't have a trailing slash OR dispute_path doesn't have a leading one
        # to avoid double slashes. reverse() usually returns a path starting with '/'.
        # A more robust way:
        # from urllib.parse import urljoin
        # response_url = urljoin(settings.SITE_URL, dispute_path)


        expert_context = {
            'dispute': dispute,
            'booking': dispute.booking,
            'response_url': response_url, # Use the correctly generated URL
        }
        
        expert_message = render_to_string('emails/expert/dispute_notification.html', expert_context)
        send_mail(
            f"Dispute Filed for Booking #{dispute.booking.id}",
            strip_tags(expert_message),
            settings.DEFAULT_FROM_EMAIL,
            [dispute.expert_email],
            html_message=expert_message,
            fail_silently=True,
        )
    
    # Email to admin
    admin_context = {
        'dispute': dispute,
        'booking': dispute.booking,
    }
    
    admin_message = render_to_string('emails/admin/dispute_notification.html', admin_context)
    send_mail(
        f"New Dispute Filed: #{dispute.id}",
        strip_tags(admin_message),
        settings.DEFAULT_FROM_EMAIL,
        [settings.ADMIN_EMAIL],
        html_message=admin_message,
        fail_silently=True,
    )

@login_required # Add login_required
@require_POST
def report_expert_noshow(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    # Permission check: Only the client who made the booking can report the expert.
    if booking.user != request.user:
        messages.error(request, "You do not have permission to report a no-show for this booking.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    # Check if booking is in a reportable state (e.g., confirmed and past schedule time)
    if booking.status != 'confirmed':
        messages.error(request, "No-show can only be reported for 'confirmed' bookings.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    if not booking.scheduled_date or not booking.scheduled_time:
        messages.error(request, "Booking schedule is incomplete. Cannot report no-show.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    scheduled_datetime_naive = datetime.combine(booking.scheduled_date, booking.scheduled_time)
    scheduled_datetime_aware = timezone.make_aware(scheduled_datetime_naive) if timezone.is_naive(scheduled_datetime_naive) else scheduled_datetime_naive

    if scheduled_datetime_aware > timezone.now():
        messages.error(request, "You can only report an expert no-show after the scheduled consultation time.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    reason = request.POST.get('reason', 'Expert did not attend the scheduled consultation.') # Default reason

    # Create or update dispute record
    dispute, created = NoShowDispute.objects.update_or_create(
        booking=booking,
        dispute_type='expert_noshow', # *** CHANGED FROM 'no_show' ***
        defaults={
            'reason': reason,
            'status': 'pending',
            # The model's save() method populates client_name, expert_name from booking
        }
    )
    if not created: # If dispute already existed (e.g. for a different reason, now re-reported as no-show)
        dispute.reason = reason # Update reason
        dispute.status = 'pending' # Reset status to pending
        dispute.reported_at = timezone.now() # Update reported time
        dispute.save()

    booking.status = 'dispute'
    booking.save(update_fields=['status'])

    send_noshow_dispute_emails(dispute) # Ensure this function is robust

    messages.success(request, "Your no-show report has been submitted. We'll review it and get back to you soon.")
    # Redirect to client bookings or booking detail page
    return redirect('expert_marketplace:client_bookings')




# expert_marketplace/views.py (add these functions)

def expert_dispute_response(request, dispute_code):
    """Allow experts to respond to disputes without logging in"""
    try:
        dispute = get_object_or_404(NoShowDispute, dispute_code=dispute_code)
        
        # If already resolved or rejected, just show the page
        if dispute.status in ['resolved', 'rejected']:
            return render(request, 'expert_marketplace/dispute_response.html', {'dispute': dispute})
        
        # If expert already responded, just show the page
        if dispute.expert_response:
            return render(request, 'expert_marketplace/dispute_response.html', {'dispute': dispute})
        
        # Handle form submission
        if request.method == 'POST':
            expert_response = request.POST.get('expert_response')
            expert_evidence_file = request.FILES.get('expert_evidence_file')
            
            if not expert_response:
                messages.error(request, 'Please provide a response.')
                return render(request, 'expert_marketplace/dispute_response.html', {'dispute': dispute})
            
            # Update dispute
            dispute.expert_response = expert_response
            dispute.expert_response_at = timezone.now()
            dispute.status = 'expert_responded'
            
            if expert_evidence_file:
                dispute.expert_evidence_file = expert_evidence_file
            
            dispute.save()
            
            # Send notification to admin
            admin_context = {
                'dispute': dispute,
                'booking': dispute.booking,
            }
            
            admin_message = render_to_string('emails/admin/expert_dispute_response.html', admin_context)
            send_mail(
                f"Expert Response to Dispute #{dispute.id}",
                strip_tags(admin_message),
                settings.DEFAULT_FROM_EMAIL,
                [settings.ADMIN_EMAIL],
                html_message=admin_message,
                fail_silently=True,
            )
            
            messages.success(request, 'Your response has been submitted successfully. Our team will review the case.')
            return redirect('expert_marketplace:dispute_response', dispute_code=dispute_code)
        
        return render(request, 'expert_marketplace/dispute_response.html', {'dispute': dispute})
    except NoShowDispute.DoesNotExist:
        messages.error(request, 'Invalid dispute code. Please check the link and try again.')
        return redirect('expert_marketplace:home')



@require_POST
@login_required
def report_client_noshow(request, booking_id):
    """Report that a client didn't show up for a consultation (expert only)"""
    booking = get_object_or_404(Booking, id=booking_id)

    try:
        expert_profile = request.user.expert_profile
        if booking.expert != expert_profile:
            messages.error(request, "You are not the assigned expert for this booking.")
            return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
    except (AttributeError, Expert.DoesNotExist): # Make sure Expert.DoesNotExist is imported or handled
        messages.error(request, "You must be an expert to perform this action.")
        return redirect('expert_marketplace:expert_login') # Ensure this URL name is correct

    if booking.status != 'confirmed':
        messages.error(request, "Client no-show can only be reported for confirmed bookings.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    if not booking.scheduled_date or not booking.scheduled_time:
        messages.error(request, "Booking schedule is incomplete and cannot report no-show.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    # CORRECTED LINE:
    # Assuming 'from datetime import datetime'
    scheduled_datetime_naive = datetime.combine(booking.scheduled_date, booking.scheduled_time)
    scheduled_datetime_aware = timezone.make_aware(scheduled_datetime_naive) if timezone.is_naive(scheduled_datetime_naive) else scheduled_datetime_naive
    
    # If you used 'import datetime' (without 'as dt'), then it would be:
    # scheduled_datetime_naive = datetime.datetime.combine(booking.scheduled_date, booking.scheduled_time)
    # But the error suggests the former.

    if scheduled_datetime_aware > timezone.now():
        messages.error(request, "You can only report a client no-show after the scheduled consultation time.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    reason = request.POST.get('reason', 'Client did not attend the scheduled consultation.')

    dispute, created = NoShowDispute.objects.get_or_create(
        booking=booking,
        dispute_type='client_noshow',
        defaults={
            'reason': reason,
            'status': 'pending',
            'client_name': booking.name or (booking.user.get_full_name() if booking.user else "N/A"),
            'client_email': booking.email or (booking.user.email if booking.user else "N/A"),
            'expert_name': booking.expert.full_name, # Assuming expert has full_name
            'expert_email': booking.expert.email,    # Assuming expert has email
            'reported_at': timezone.now()
        }
    )

    if not created: # If dispute already existed
        if dispute.status in ['resolved', 'rejected']:
             messages.info(request, "A dispute for this booking has already been resolved or rejected.")
             return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
        # Update reason and ensure it's pending if re-reported
        dispute.reason = f"Original: {dispute.reason}\nUpdate/Re-report by expert: {reason}"
        dispute.status = 'pending'
        dispute.reported_at = timezone.now() # Update reported time
        dispute.save()
        messages.info(request, "Client no-show report updated.")
    else:
        messages.success(request, "Client no-show reported. This will be reviewed by our team.")

    booking.status = 'dispute'
    booking.save(update_fields=['status'])

    # Ensure send_noshow_dispute_emails is defined and handles the dispute object correctly
    send_noshow_dispute_emails(dispute)

    return redirect('expert_marketplace:booking_detail', booking_id=booking.id)




@login_required # Ensure this decorator is present
def reschedule_booking(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    
    # ... (all existing permission checks, status checks, reschedule_count check remain the same) ...
    # Ensure scheduled_date and scheduled_time are not None
    if not booking.scheduled_date or not booking.scheduled_time:
        messages.error(request, "Booking schedule is incomplete and cannot be rescheduled.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    scheduled_datetime = datetime.combine(booking.scheduled_date, booking.scheduled_time)
    if timezone.is_naive(scheduled_datetime): 
        scheduled_datetime = timezone.make_aware(scheduled_datetime)

    if scheduled_datetime < timezone.now():
        messages.error(request, "You cannot reschedule a past booking.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
    
    if booking.reschedule_count >= 3:
        # ... (your existing logic for max reschedules - this is correct) ...
        # (processes 50% refund and cancels)
        # For brevity, I'm not repeating the full block here.
        # Ensure it redirects after processing.
        # Example:
        if booking.stripe_charge_id or booking.stripe_payment_intent_id:
            refund_to_process_decimal = booking.consultation_fee * Decimal('0.5')
            logger.info(f"Auto-cancelling booking {booking.id} due to reschedule limit. Processing 50% refund: £{refund_to_process_decimal:.2f}")
            success, refund_details_or_error = process_stripe_refund(
                booking=booking,
                amount_decimal=refund_to_process_decimal,
                reason="Auto-cancelled: Maximum reschedule limit reached (3)"
            )
            if success:
                booking.cancellation_reason = "Maximum reschedule limit reached (3)"
                booking.cancelled_by = 'system'
                booking.save(update_fields=['cancellation_reason', 'cancelled_by']) # Status, refund_amount, cancelled_at updated by service
                send_cancellation_emails(booking)
                messages.info(request, f"Booking auto-cancelled. 50% refund of £{booking.refund_amount:.2f} processed.")
            else:
                # ... (error handling for refund failure) ...
                logger.error(f"Stripe refund FAILED for booking {booking.id} during auto-cancellation. Error: {refund_details_or_error}")
                messages.error(request, f"Booking auto-cancellation attempted, but Stripe refund FAILED: {refund_details_or_error}. Contact support.")
                booking.status = 'cancelled_refund_failed' 
                booking.cancellation_reason = "Max reschedules; refund failed."
                booking.cancelled_at = timezone.now()
                booking.cancelled_by = 'system'
                booking.save()
        else:
            # ... (logic for no payment to refund) ...
            booking.status = 'cancelled'
            booking.cancellation_reason = "Maximum reschedule limit reached (3)"
            booking.cancelled_at = timezone.now()
            booking.cancelled_by = 'system'
            booking.refund_amount = Decimal('0.00')
            booking.save()
            send_cancellation_emails(booking)
            messages.info(request, "Booking auto-cancelled (no payment to refund).")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)


    if request.method == 'POST':
        try:
            new_date_str = request.POST.get('new_date')
            new_time_str = request.POST.get('new_time')
            
            if not new_date_str or not new_time_str:
                messages.error(request, "New date and time are required.")
                return redirect('expert_marketplace:reschedule_booking', booking_id=booking.id)

            new_date_obj = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            new_time_obj = datetime.strptime(new_time_str, '%H:%M').time()
            
            new_datetime_combined_naive = datetime.combine(new_date_obj, new_time_obj)
            new_datetime_combined_aware = timezone.make_aware(new_datetime_combined_naive) if timezone.is_naive(new_datetime_combined_naive) else new_datetime_combined_naive

            if new_datetime_combined_aware <= timezone.now():
                messages.error(request, "The new date and time must be in the future.")
                return redirect('expert_marketplace:reschedule_booking', booking_id=booking.id)
            
            original_expert = booking.expert # Store original expert
            engine = SmartAssignmentEngine()

            # Step 1: Check if the current expert is available at the new time
            current_expert_is_available = False
            if original_expert:
                logger.info(f"Reschedule Check: Checking if current expert {original_expert.id} is available for booking {booking.id} at {new_datetime_combined_aware}")
                current_expert_is_available = engine.is_expert_available(
                    original_expert, 
                    new_datetime_combined_aware, 
                    booking.duration_minutes,
                    booking_instance=booking # Pass booking to exclude itself from conflict checks if logic allows
                )
            
            if current_expert_is_available:
                logger.info(f"Reschedule: Current expert {original_expert.id} IS available. Proceeding with reschedule.")
                # Keep the same expert, just update time
                booking.scheduled_date = new_date_obj
                booking.scheduled_time = new_time_obj
                booking.reschedule_count = F('reschedule_count') + 1
                booking.save()
                booking.refresh_from_db()
                # Send reschedule notification emails
                # send_reschedule_emails(booking, old_date, old_time) # You have this logic
                messages.success(request, "Booking rescheduled successfully with your current expert.")
                # ... (your existing email sending and messages for reschedules_left) ...
                return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
            else:
                logger.info(f"Reschedule: Current expert {original_expert.id if original_expert else 'None'} is NOT available or no expert assigned. Attempting to find a new expert for booking {booking.id} at {new_date_obj} {new_time_obj}.")
                # Current expert not available, or no expert was assigned (should not happen if status is 'confirmed')
                # Try to find a new expert for the new time.
                # Temporarily update booking's time to the new time for the engine to use
                booking.scheduled_date = new_date_obj
                booking.scheduled_time = new_time_obj
                # We need to save these temporary changes if assign_expert relies on them being in DB,
                # or ensure assign_expert can take date/time overrides.
                # For now, let's assume assign_expert uses the booking object's fields.
                
                # Exclude the original expert if they were the one who wasn't available
                expert_to_exclude = original_expert.id if original_expert else None
                
                new_assigned_expert, error_message = engine.assign_expert(booking, expert_to_exclude_id=expert_to_exclude)

                if new_assigned_expert:
                    logger.info(f"Reschedule: Found new expert {new_assigned_expert.id} for booking {booking.id} at new time.")
                    booking.expert = new_assigned_expert # Assign the new expert
                    booking.assigned_at = timezone.now() # Update assigned_at if changing expert
                    booking.reschedule_count = F('reschedule_count') + 1
                    # scheduled_date and scheduled_time are already set to new values
                    booking.save()
                    booking.refresh_from_db()
                    messages.success(request, f"Booking rescheduled successfully with a new expert: {new_assigned_expert.full_name}.")
                    # Send reschedule notification emails (to client, new expert, old expert if applicable)
                    # send_reschedule_emails(...)
                    # ... (your existing email sending and messages for reschedules_left) ...
                    return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
                else:
                    logger.warning(f"Reschedule: No expert (current or new) available for booking {booking.id} at {new_date_obj} {new_time_obj}. Error: {error_message}. Proceeding to refund.")
                    # No expert available at the new time. Refund the client (full refund as per implied rule).
                    # Revert booking time to original for record-keeping before cancellation, or log original time.
                    # For simplicity, we'll cancel with the new time recorded as the "attempted reschedule time".
                    
                    booking.status = 'cancelled'
                    booking.cancellation_reason = f"Client attempted to reschedule to {new_date_obj} {new_time_obj}, but no expert was available. Original expert: {original_expert.full_name if original_expert else 'N/A'}. Engine message: {error_message}"
                    booking.cancelled_at = timezone.now()
                    booking.cancelled_by = 'system_reschedule_fail' # Or 'client_reschedule_fail'
                    
                    if booking.stripe_charge_id or booking.stripe_payment_intent_id:
                        # Assuming full refund if reschedule fails due to no availability
                        success_refund, refund_details = process_stripe_refund(
                            booking=booking,
                            amount_decimal=booking.consultation_fee, # Full refund
                            reason=f"Reschedule failed for booking {booking.id}: No expert available at new time."
                        )
                        if success_refund:
                            messages.error(request, f"We couldn't find any expert available for the new time. Your booking has been cancelled and a full refund of £{booking.refund_amount:.2f} is being processed.")
                        else:
                            messages.error(request, f"We couldn't find any expert for the new time. Booking cancelled, but refund failed: {refund_details}. Please contact support.")
                            booking.status = 'cancelled_refund_failed' # Special status
                    else:
                        messages.error(request, "We couldn't find any expert available for the new time. Your booking has been cancelled (no payment was recorded).")
                    
                    booking.save()
                    send_cancellation_emails(booking) # Notify about cancellation
                    return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

        except (ValueError, TypeError) as e:
            # ... (your existing error handling for invalid date/time format) ...
            logger.error(f"Error rescheduling booking {booking_id}: Invalid date/time format or other type error: {str(e)}")
            messages.error(request, f"Invalid date or time format provided.")
            return redirect('expert_marketplace:reschedule_booking', booking_id=booking.id)
        except Exception as e:
            # ... (your existing general error handling) ...
            logger.error(f"Unexpected error rescheduling booking {booking_id}: {str(e)}", exc_info=True)
            messages.error(request, "An unexpected error occurred while rescheduling.")
            return redirect('expert_marketplace:reschedule_booking', booking_id=booking.id)

    # ... (rest of your GET request handling for the reschedule_booking view) ...
    available_slots = get_available_time_slots() 
    context = {
        'booking': booking,
        'available_slots': available_slots,
        'reschedules_remaining': 3 - booking.reschedule_count,
    }
    return render(request, 'expert_marketplace/reschedule_booking.html', context)







@login_required
def mark_meeting_complete(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
  
    is_client_actor = booking.user == request.user 
    is_staff_actor = request.user.is_staff

    if not (is_client_actor or is_staff_actor):
        messages.error(request, "You don't have permission to modify this consultation.")
        return redirect('expert_marketplace:client_bookings') # Or appropriate redirect

    if booking.status not in ['confirmed', 'completed']:
        messages.error(request, f"This booking (status: {booking.get_status_display()}) cannot be marked as complete or reviewed at this time.")
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    if booking.status == 'confirmed':
        scheduled_dt_aware = booking.get_scheduled_datetime_aware() 
        if not scheduled_dt_aware:
            messages.error(request, "Booking schedule is incomplete and cannot be marked complete.")
            return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
        if scheduled_dt_aware > timezone.now(): # Check if meeting time has passed
            messages.error(request, "You can only mark a meeting as completed after its scheduled time has passed.")
            return redirect('expert_marketplace:booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        client_rating_str = request.POST.get('client_rating_for_expert')
        client_review_text = request.POST.get('client_review_for_expert', '').strip()
        staff_completion_notes_from_post = ""
        if is_staff_actor and not is_client_actor: # Staff acting alone
            staff_completion_notes_from_post = request.POST.get('completion_notes', '').strip()

        client_rating_value = None
        if is_client_actor: # Only clients provide ratings through this form
            if not client_rating_str: 
                messages.error(request, "A star rating is required to mark the consultation as complete.")
                # Redirect back to the form, ideally preserving other input if the form was complex
                return redirect(request.META.get('HTTP_REFERER', reverse('expert_marketplace:booking_detail', args=[booking.id])))
            try:
                client_rating_value = int(client_rating_str)
                if not (1 <= client_rating_value <= 5): raise ValueError("Rating out of range.")
            except (ValueError, TypeError):
                messages.error(request, "Invalid rating value submitted. Please select 1 to 5 stars.")
                return redirect(request.META.get('HTTP_REFERER', reverse('expert_marketplace:booking_detail', args=[booking.id])))

        # Update or Create Consultation record
        scheduled_start_time_for_consultation = booking.get_scheduled_datetime_aware()
        consultation_defaults = {
            'expert': booking.expert, 
            'user': booking.user,
            'scheduled_start_time': scheduled_start_time_for_consultation, 
            'status': 'completed', # Mark consultation as completed
        }
        if is_client_actor:
            consultation_defaults['client_rating_for_expert'] = client_rating_value
            consultation_defaults['client_review_for_expert'] = client_review_text
        
        # If staff is completing, they might add notes.
        # These could go to Consultation.notes_by_expert or a general admin_notes field.
        if is_staff_actor and staff_completion_notes_from_post:
            consultation_defaults['notes_by_expert'] = (consultation_defaults.get('notes_by_expert', '') + " " + staff_completion_notes_from_post).strip()


        consultation_record, cr_created = Consultation.objects.update_or_create(
            booking=booking, 
            defaults=consultation_defaults
        )
        logger.info(f"Consultation record {'created' if cr_created else 'updated'} for booking {booking.id}.")

        if booking.status == 'confirmed': # First time marking as complete
            booking.status = 'completed'
            booking.completed_at = timezone.now()
            update_fields_for_booking = ['status', 'completed_at']
            
            if is_staff_actor and staff_completion_notes_from_post:
                booking.completion_notes = (booking.completion_notes or "") + " " + staff_completion_notes_from_post
                update_fields_for_booking.append('completion_notes')

            booking.save(update_fields=list(set(update_fields_for_booking))) # Use set to avoid duplicates
            logger.info(f"Booking {booking.id} status changed to 'completed'.")

            if booking.expert:
                booking.calculate_financials(and_save=True) # Ensure financials are up-to-date
                booking.refresh_from_db(fields=['expert_earnings', 'platform_fee'])

                if booking.expert_earnings is not None and booking.expert_earnings > Decimal('0.00'):
                    try:
                        earning, earning_created = ExpertEarning.objects.update_or_create(
                            booking=booking,
                            expert=booking.expert,
                            defaults={
                                'amount': booking.expert_earnings,
                                'platform_fee_recorded': booking.platform_fee,
                                'status': ExpertEarning.PENDING, # Earnings are now PENDING for weekly payout
                                'calculated_at': timezone.now(),
                                'notes': "Earning recorded upon consultation completion."
                            }
                        )
                        logger.info(f"ExpertEarning {'CREATED' if earning_created else 'UPDATED to PENDING'} for booking {booking.id}. Amount: {earning.amount}")
                        
                        expert_profile = booking.expert
                        if earning_created: # Only add to total_earnings if newly created
                             expert_profile.total_earnings = (expert_profile.total_earnings or Decimal('0.00')) + earning.amount
                        
                        # Recalculate pending_payout based on all PENDING earnings for this expert
                        current_pending_sum = ExpertEarning.objects.filter(
                            expert=expert_profile, status=ExpertEarning.PENDING
                        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                        expert_profile.pending_payout = current_pending_sum
                        expert_profile.save(update_fields=['total_earnings', 'pending_payout'])
                            
                    except Exception as e:
                        logger.error(f"Error processing ExpertEarning for booking {booking.id} on completion: {str(e)}")
                        messages.warning(request, f"Consultation marked complete, but an issue occurred while recording expert earnings: {str(e)}")
                else:
                    logger.warning(f"Expert earnings for booking {booking.id} is zero or None. No ExpertEarning record created/updated.")
            
            send_completion_emails(booking) # Send relevant completion notifications
            messages.success(request, "Consultation marked as complete successfully. Thank you for your feedback!")

        elif booking.status == 'completed' and is_client_actor: # Client updating review for already completed booking
            # The Consultation record was already updated above with new review/rating
            messages.success(request, "Thank you! Your review has been updated.")
            logger.info(f"Review updated by client for already completed booking {booking.id}.")
        
        # NO IMMEDIATE PAYOUT ATTEMPT HERE. This is handled by the weekly payout command.
      
        return redirect('expert_marketplace:booking_detail', booking_id=booking.id)
  
    # GET request handling
    context = {'booking': booking}
    if is_staff_actor and booking.status == 'confirmed':
        # Staff might have a specific template to mark complete if they add notes
        return render(request, 'expert_marketplace/mark_consultation_complete_staff.html', context) # Example template
    elif is_client_actor and booking.status in ['confirmed', 'completed']:
        # Client uses a modal or a page that includes review submission
        # This part depends on how your "leave review" modal is triggered.
        # If it's part of booking_detail, this view might only handle the POST.
        # For now, assume the form is on booking_detail or a dedicated review page.
        pass # Handled by redirect or modal on another page

    # Fallback or if GET request is not for a specific form display by this view
    messages.info(request, "To leave or update a review, please use the options on the booking details page.")
    return redirect('expert_marketplace:booking_detail', booking_id=booking.id)





        

        
def respond_to_dispute(request, dispute_code):
    """Allow experts to respond to disputes via email link (no login required)"""
    try:
        dispute = NoShowDispute.objects.get(dispute_code=dispute_code)
    except NoShowDispute.DoesNotExist:
        return render(request, 'dispute_response_error.html', {
            'error': 'Invalid dispute code. This dispute may have been resolved or cancelled.'
        })
    
    # Check if dispute can still be responded to
    if dispute.status != 'pending':
        return render(request, 'dispute_response_error.html', {
            'error': 'This dispute has already been responded to or resolved.'
        })
    
    # Check if response window has expired (24 hours)
    if timezone.now() - dispute.reported_at > timedelta(hours=24):
        return render(request, 'dispute_response_error.html', {
            'error': 'The response window for this dispute has expired.'
        })
    
    if request.method == 'POST':
        response = request.POST.get('response', '')
        
        # Update dispute
        dispute.expert_response = response
        dispute.expert_response_at = timezone.now()
        dispute.status = 'expert_responded'
        
        # Handle evidence file
        if 'evidence_file' in request.FILES:
            dispute.expert_evidence_file = request.FILES['evidence_file']
        
        dispute.save()
        
        # Send notification to admin
        send_dispute_response_notification(dispute)
        
        return render(request, 'dispute_response_success.html', {
            'dispute': dispute
        })
    
    return render(request, 'dispute_response.html', {
        'dispute': dispute,
        'booking': dispute.booking
    })


def expert_login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'is_expert_user') and request.user.is_expert_user:
            return redirect('expert_marketplace:expert_dashboard')
        else:
            messages.info(request, "You are already logged in with a different account type.")
            # Decide where to redirect non-experts: client dashboard or logout then expert login
            return redirect('expert_marketplace:client_bookings') # Or 'home' or 'account_logout'

    if request.method == 'POST':
        # Using a custom form or just getting data directly
        email = request.POST.get('username') # Assuming your form field for email is 'username'
        password = request.POST.get('password')

        if not email or not password:
            messages.error(request, "Please enter both email and password.")
            form = ExpertLoginForm(request.POST) # Re-populate form for display
            return render(request, 'expert_marketplace/expert_login.html', {'form': form, 'page_title': 'Expert Login'})

        user = authenticate(request, username=email, password=password)

        if user is not None:
            # IMPORTANT: Check if authentication came from ExpertAuthBackend
            if hasattr(user, 'is_expert_user') and user.is_expert_user:
                expert_profile = user.expert_profile # Get the expert profile attached by the backend
                if expert_profile.is_active:
                    auth_login(request, user) # Log in the user object (which is linked to the expert)
                    messages.success(request, f"Welcome back, {expert_profile.first_name}!")
                    return redirect(request.GET.get('next') or 'expert_marketplace:expert_dashboard')
                else:
                    messages.error(request, "Your expert account is currently inactive. Please contact support.")
            else:
                # User authenticated, but not via ExpertAuthBackend (e.g., regular user)
                messages.error(request, "This login is for registered experts only. Please use the client login if you are a client.")
        else:
            # Authentication failed entirely
            messages.error(request, "Invalid email or password. Please try again.")
    
    # For GET request or if POST fails before authentication
    form = ExpertLoginForm() # Create an instance of your expert login form
    return render(request, 'expert_marketplace/expert_login.html', {
        'form': form, 
        'page_title': 'Expert Login'
    })




@login_required
def expert_logout_view(request):
    auth_logout(request)
    messages.info(request, "You have been successfully logged out.")
    return redirect('expert_marketplace:expert_login')

@login_required
def expert_dashboard_view(request):
    try:
        expert_profile = request.user.expert_profile 
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request)
            return redirect('expert_marketplace:expert_login')
    except AttributeError: 
        messages.error(request, "Access denied. This dashboard is for active experts only.")
        auth_logout(request) 
        return redirect('expert_marketplace:expert_login')
    except Expert.DoesNotExist: 
        messages.error(request, "Expert profile not found. Please contact support.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login')

    upcoming_bookings = Booking.objects.filter(
        expert=expert_profile, 
        status='confirmed', # Make sure 'confirmed' is a valid status in your Booking model
        scheduled_date__gte=timezone.now().date()
    ).select_related('user').order_by('scheduled_date', 'scheduled_time') # Added select_related for user
    
    # Fetch recent completed bookings and prefetch their earning records
    recent_completed_bookings_qs = Booking.objects.filter(
        expert=expert_profile,
        status='completed' # Make sure 'completed' is a valid status
    ).select_related('user').prefetch_related( # Added select_related and prefetch_related
        # Corrected line:
        Prefetch('expert_earning_record', queryset=ExpertEarning.objects.all(), to_attr='earning_record_list')
    ).order_by('-completed_at')[:5]
    
    # Process to add actual_earning to each booking
    processed_completed_bookings = []
    for booking in recent_completed_bookings_qs:
        if hasattr(booking, 'earning_records_list') and booking.earning_records_list:
            # Assuming one ExpertEarning record per booking
            booking.actual_earning = booking.earning_records_list[0].amount 
        else:
            # Fallback: Calculate if ExpertEarning record is missing (should ideally not happen for completed)
            # This assumes expert_profile.commission_rate is the platform's take (e.g., 0.4 for 40%)
            # So, expert's share is (1 - commission_rate)
            expert_share_rate = Decimal('1.00') - (expert_profile.commission_rate or Decimal('0.00'))
            booking.actual_earning = (booking.consultation_fee or Decimal('0.00')) * expert_share_rate
            booking.actual_earning = booking.actual_earning.quantize(Decimal('0.01'))
            # Log a warning if an earning record was expected but not found
            if booking.status == 'completed':
                 print(f"Warning: ExpertEarning record not found for completed booking ID {booking.id}. Calculated earning as fallback.") # Replace with proper logging
        processed_completed_bookings.append(booking)
    
    context = {
        'expert': expert_profile,
        'upcoming_bookings': upcoming_bookings,
        'recent_completed_bookings': processed_completed_bookings, # Use the processed list
        'page_title': 'Expert Dashboard'
    }
    return render(request, 'expert_marketplace/expert_dashboard.html', context)



@login_required
def expert_past_consultations_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request)
            return redirect('expert_marketplace:expert_login')
    except (AttributeError, Expert.DoesNotExist): # Combined exceptions
        messages.error(request, "Access denied or expert profile not found. This view is for active experts only.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login')

    # Base queryset: all bookings for the expert that are in the past
    # "Past" means the scheduled_date is before the current date.
    base_query = Booking.objects.filter(
        expert=expert_profile,
        scheduled_date__lt=timezone.now().date()
    )

    # Get status filter from GET request
    status_filter_from_request = request.GET.get('status', 'all') # Default to 'all'

    # Apply status filter if a valid status is provided
    current_consultations_query = base_query
    if status_filter_from_request != 'all':
        # Check if the provided status is a valid choice
        valid_status_keys = [s[0] for s in Booking.STATUS_CHOICES]
        if status_filter_from_request in valid_status_keys:
            current_consultations_query = base_query.filter(status=status_filter_from_request)
        else:
            # If an invalid status is passed, default to 'all' but log it or message user
            logger.warning(f"Invalid status filter '{status_filter_from_request}' received. Defaulting to 'all'.")
            status_filter_from_request = 'all' # Reset for context

    consultations = current_consultations_query.order_by('-scheduled_date', '-scheduled_time')

    # Calculate statistics based on the *currently displayed* (filtered) consultations
    total_displayed = consultations.count()
    completed_count = consultations.filter(status='completed').count()
    
    # Define "cancelled" broadly for stats, including refunded
    cancelled_statuses = ['cancelled', 'cancelled_by_client', 'cancelled_by_expert', 'refunded']
    cancelled_count = consultations.filter(status__in=cancelled_statuses).count()
    
    dispute_count = consultations.filter(status='dispute').count()
    # For a more accurate dispute count, you might query NoShowDispute model related to these bookings
    # e.g., active_dispute_count = NoShowDispute.objects.filter(booking__in=consultations, status__in=['pending', 'expert_responded']).count()

    context = {
        'expert': expert_profile,
        'consultations': consultations,
        'page_title': 'Past Consultations',
        'active_nav': 'past_consultations',
        'status_choices': Booking.STATUS_CHOICES,  # For the filter dropdown
        'current_status_filter': status_filter_from_request, # To select the current filter in dropdown
        'stats': {
            'total_displayed': total_displayed,
            'completed': completed_count,
            'cancelled_or_refunded': cancelled_count, # Renamed for clarity
            'in_dispute': dispute_count, # This counts bookings currently with status 'dispute'
        }
    }
    return render(request, 'expert_marketplace/expert_past_consultations.html', context)



@login_required
def expert_upcoming_consultations_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request)
            return redirect('expert_marketplace:expert_login')
    except AttributeError: 
        messages.error(request, "Access denied. This view is for active experts only.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login')
    except Expert.DoesNotExist: 
        messages.error(request, "Expert profile not found. Please contact support.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login')

    upcoming_consultations = Booking.objects.filter(
        expert=expert_profile,
        status__in=['confirmed', 'pending_payment'], 
        scheduled_date__gte=timezone.now().date()
    ).order_by('scheduled_date', 'scheduled_time')
    
    context = {
        'expert': expert_profile,
        'consultations': upcoming_consultations,
        'page_title': 'Upcoming Consultations',
        'active_nav': 'upcoming_consultations' 
    }
    return render(request, 'expert_marketplace/expert_upcoming_consultations.html', context)

@login_required
def expert_past_consultations_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive. Please contact support.")
            auth_logout(request)
            return redirect('expert_marketplace:expert_login')
        logger.debug(f"Expert Past Consultations: Processing for expert '{expert_profile.full_name}' (ID: {expert_profile.id})")
    except (AttributeError, Expert.DoesNotExist): 
        messages.error(request, "Access denied. This page is for active experts only or your profile is not found.")
        auth_logout(request) 
        return redirect('expert_marketplace:expert_login')

    today = timezone.now().date()
    logger.debug(f"Expert Past Consultations: Current date for 'past' comparison: {today}")

    base_query = Booking.objects.filter(
        expert=expert_profile,
        scheduled_date__lt=today
    )
    logger.debug(f"Expert Past Consultations: Base query (expert_id={expert_profile.id}, scheduled_date < {today}) count: {base_query.count()}")

    status_filter_from_request = request.GET.get('status', 'all') 
    logger.debug(f"Expert Past Consultations: Status filter from request: '{status_filter_from_request}'")

    current_consultations_query = base_query
    if status_filter_from_request != 'all':
        valid_status_keys = [s[0] for s in Booking.STATUS_CHOICES]
        if status_filter_from_request in valid_status_keys:
            current_consultations_query = base_query.filter(status=status_filter_from_request)
            logger.debug(f"Expert Past Consultations: Applied status filter '{status_filter_from_request}'. Filtered query count: {current_consultations_query.count()}")
        else:
            logger.warning(f"Expert Past Consultations: Invalid status filter '{status_filter_from_request}' received. Defaulting to 'all'.")
            status_filter_from_request = 'all' 

    consultations = current_consultations_query.order_by('-scheduled_date', '-scheduled_time')
    logger.debug(f"Expert Past Consultations: Final consultations count to be displayed: {consultations.count()}")

    total_displayed = consultations.count()
    completed_count = consultations.filter(status='completed').count()
    
    cancelled_statuses = ['cancelled', 'cancelled_by_client', 'cancelled_by_expert', 'refunded', 'partially_refunded', 'expert_noshow', 'client_noshow']
    cancelled_count = consultations.filter(status__in=cancelled_statuses).count()
    
    dispute_count = consultations.filter(status='dispute').count()
    
    stats_data = {
        'total_displayed': total_displayed,
        'completed': completed_count,
        'cancelled_or_refunded': cancelled_count, 
        'in_dispute': dispute_count,
    }
    logger.debug(f"Expert Past Consultations: Stats data: {stats_data}")

    context = {
        'expert': expert_profile,
        'consultations': consultations,
        'page_title': 'Past Consultations',
        'active_nav': 'past_consultations',
        'status_choices': Booking.STATUS_CHOICES,
        'current_status_filter': status_filter_from_request,
        'stats': stats_data
    }
    return render(request, 'expert_marketplace/expert_past_consultations.html', context)


@login_required
def expert_availability_list_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request)
            return redirect('expert_marketplace:expert_login')
    except AttributeError:
        messages.error(request, "Access denied. This view is for active experts only.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login')
    except Expert.DoesNotExist:
        messages.error(request, "Expert profile not found. Please contact support.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login')

    availabilities = []
    if expert_profile.availability_json:
        try:
            availabilities_data = json.loads(expert_profile.availability_json)
            if isinstance(availabilities_data, list):
                availabilities = sorted(
                    availabilities_data,
                    key=lambda x: (
                        datetime.strptime(x.get('date', '1900-01-01'), '%Y-%m-%d'), 
                        datetime.strptime(x.get('start_time', '00:00'), '%H:%M') 
                    )
                )
            else:
                logger.warning(f"Expert {expert_profile.id} availability_json is not a list: {expert_profile.availability_json}")
                messages.error(request, "Availability data is not in the expected list format.")
        except json.JSONDecodeError:
            logger.error(f"Malformed JSON in availability_json for expert {expert_profile.id}: {expert_profile.availability_json}")
            messages.error(request, "Could not load availability data due to a format error.")
        except (KeyError, ValueError) as e:
            logger.error(f"Error processing availability slot data for expert {expert_profile.id}: {e}. Data: {expert_profile.availability_json}")
            messages.error(request, f"Error processing availability slot data: {e}")

    context = {
        'expert': expert_profile,
        'availabilities': availabilities, 
        'page_title': 'My Availability',
        'active_nav': 'my_availability' 
    }
    return render(request, 'expert_marketplace/expert_availability_list.html', context)

@login_required
def expert_profile_settings_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request) 
            return redirect('expert_marketplace:expert_login')
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Access denied or expert profile not found. This view is for active experts only.")
        auth_logout(request) 
        return redirect('expert_marketplace:expert_login')

    profile_form_submitted = 'update_profile' in request.POST
    password_form_submitted = 'change_password' in request.POST
    availability_form_submitted = 'update_availability' in request.POST

    profile_form = ExpertProfileUpdateForm(instance=expert_profile)
    password_form = ExpertPasswordChangeForm(expert=expert_profile)
    
    current_availability_json_for_js = expert_profile.availability_json
    availability_form = ExpertAvailabilityJSONForm(
        initial={'availability_json_string': current_availability_json_for_js}
    )

    if request.method == 'POST':
        if profile_form_submitted:
            profile_form = ExpertProfileUpdateForm(request.POST, request.FILES, instance=expert_profile)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Your profile has been updated successfully.')
                return redirect('expert_marketplace:expert_profile_settings')
            availability_form = ExpertAvailabilityJSONForm(initial={'availability_json_string': expert_profile.availability_json})

        elif password_form_submitted:
            password_form = ExpertPasswordChangeForm(expert=expert_profile, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                # Important: Update session auth hash to prevent logout after password change
                update_session_auth_hash(request, password_form.expert) # Use password_form.expert which is the expert instance
                messages.success(request, 'Your password has been changed successfully.')
                return redirect('expert_marketplace:expert_profile_settings')
            availability_form = ExpertAvailabilityJSONForm(initial={'availability_json_string': expert_profile.availability_json})
            
        elif availability_form_submitted:
            availability_form = ExpertAvailabilityJSONForm(request.POST) 
            if availability_form.is_valid():
                cleaned_json_string = availability_form.cleaned_data['availability_json_string']
                expert_profile.availability_json = cleaned_json_string
                expert_profile.save(update_fields=['availability_json'])
                messages.success(request, 'Your availability settings have been updated successfully.')
                current_availability_json_for_js = cleaned_json_string 
                return redirect('expert_marketplace:expert_profile_settings')
            profile_form = ExpertProfileUpdateForm(instance=expert_profile) 
            password_form = ExpertPasswordChangeForm(expert=expert_profile) 

    context = {
        'expert': expert_profile,
        'profile_form': profile_form,
        'password_form': password_form,
        'availability_form': availability_form, 
        'current_availability_json_for_js': current_availability_json_for_js, 
        'page_title': 'Profile Settings',
        'active_nav': 'profile_settings'
    }
    return render(request, 'expert_marketplace/expert_profile_settings.html', context)






@login_required
def expert_earnings_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request) # Use the aliased logout
            return redirect('expert_marketplace:expert_login')
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Access denied or expert profile not found.")
        auth_logout(request) # Use the aliased logout
        return redirect('expert_marketplace:expert_login')

    # --- Stripe Account Information ---
    stripe_connected = bool(expert_profile.stripe_account_id)
    stripe_account_details_summary = "Not Connected"
    stripe_onboarding_needed = True 
    stripe_payouts_ready_for_schedule = False # Key flag for weekly payouts
    stripe_login_link_available = False
    stripe_account_issues = []

    if stripe_connected:
        try:
            stripe_service = StripePaymentService() # Assuming you have this class
            stripe_account = stripe_service.get_account_details(expert_profile.stripe_account_id) # Use service method

            if stripe_account:
                payouts_enabled_on_stripe = stripe_account.get('payouts_enabled', False)
                details_submitted_on_stripe = stripe_account.get('details_submitted', False)
                
                # Update expert model from Stripe source of truth
                expert_profile.stripe_details_submitted = details_submitted_on_stripe
                expert_profile.stripe_charges_enabled = stripe_account.get('charges_enabled', False) # Though less relevant for payouts
                expert_profile.stripe_payouts_enabled_status = payouts_enabled_on_stripe # Store the direct status
                expert_profile.save(update_fields=['stripe_details_submitted', 'stripe_charges_enabled', 'stripe_payouts_enabled_status'])


                if payouts_enabled_on_stripe and details_submitted_on_stripe:
                    stripe_account_details_summary = "Payouts Enabled & Ready"
                    stripe_payouts_ready_for_schedule = True # Ready for weekly payouts
                    stripe_onboarding_needed = False
                    stripe_login_link_available = True
                elif details_submitted_on_stripe and not payouts_enabled_on_stripe:
                    stripe_account_details_summary = "Verification Pending or Restricted"
                    stripe_account_issues.append("Your Stripe account requires further verification or has restrictions. Please manage your Stripe account to enable payouts.")
                    stripe_login_link_available = True
                    stripe_onboarding_needed = True 
                elif not details_submitted_on_stripe:
                    stripe_account_details_summary = "Onboarding Incomplete"
                    stripe_account_issues.append("Your Stripe account onboarding is incomplete. Please complete the setup via Stripe.")
                    stripe_onboarding_needed = True
                else: 
                    stripe_account_details_summary = "Status Check Needed - Manage Account"
                    stripe_account_issues.append("Please review your Stripe account status.")
                    stripe_login_link_available = True
                    stripe_onboarding_needed = True

                requirements = stripe_account.get('requirements', {})
                if requirements:
                    if requirements.get('disabled_reason'):
                        stripe_account_issues.append(f"Account disabled: {requirements['disabled_reason']}")
                        stripe_payouts_ready_for_schedule = False # Explicitly false if disabled
                    currently_due = requirements.get('currently_due', [])
                    if currently_due:
                        stripe_account_issues.append(f"Action required: Please update information for {', '.join(currently_due)} in your Stripe dashboard.")
                        stripe_onboarding_needed = True
                        stripe_payouts_ready_for_schedule = False # Not ready if info due
                    past_due = requirements.get('past_due', [])
                    if past_due:
                         stripe_account_issues.append(f"Past due: Please update information for {', '.join(past_due)} in your Stripe dashboard immediately.")
                         stripe_onboarding_needed = True
                         stripe_payouts_ready_for_schedule = False # Not ready if info past due
            else:
                stripe_account_details_summary = "Error fetching Stripe status (account not found by service)"
                stripe_account_issues.append("Could not retrieve your Stripe account details at this time.")

        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error retrieving account for expert {expert_profile.id}: {str(e)}")
            stripe_account_details_summary = "Error fetching Stripe status"
            stripe_account_issues.append(f"Could not retrieve your Stripe account details: {str(e)}")
        except Exception as e:
            logger.error(f"Generic error retrieving Stripe account for expert {expert_profile.id}: {str(e)}")
            stripe_account_details_summary = "Error fetching Stripe status"
            stripe_account_issues.append("An unexpected error occurred while fetching Stripe details.")

    # --- Earnings Data ---
    # Recalculate pending_payout from source of truth to be sure
    expert_profile.pending_payout = ExpertEarning.objects.filter(
        expert=expert_profile, status=ExpertEarning.PENDING
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    expert_profile.save(update_fields=['pending_payout']) # Save if changed

    pending_payout_amount = expert_profile.pending_payout
    total_lifetime_earnings = expert_profile.total_earnings or Decimal('0.00')

    pending_earnings_records = ExpertEarning.objects.filter(
        expert=expert_profile, status=ExpertEarning.PENDING
    ).select_related('booking__user').order_by('-calculated_at') # Added booking.user for template

    pending_bonuses_records = ExpertBonus.objects.filter(
        expert=expert_profile, status=ExpertBonus.PENDING
    ).order_by('-created_at')

    # --- Payout History (Grouped by Stripe Transfer) ---
    paid_earnings_q = ExpertEarning.objects.filter(expert=expert_profile, status=ExpertEarning.PAID, transaction_id__isnull=False).select_related('booking__user')
    paid_bonuses_q = ExpertBonus.objects.filter(expert=expert_profile, status=ExpertBonus.PAID, transaction_id__isnull=False)

    all_paid_items = sorted(
        list(paid_earnings_q) + list(paid_bonuses_q),
        key=attrgetter('paid_at', 'transaction_id'), reverse=True
    )

    payout_history_grouped = []
    for transaction_id, group in groupby(all_paid_items, key=attrgetter('transaction_id')):
        if not transaction_id: continue
        
        items_in_payout = list(group)
        total_paid_for_this_tx = sum(item.amount for item in items_in_payout)
        actual_paid_at_for_tx = items_in_payout[0].paid_at if items_in_payout else None
        currency = items_in_payout[0].currency if items_in_payout and hasattr(items_in_payout[0], 'currency') else expert_profile.currency

        payout_history_grouped.append({
            'transaction_id': transaction_id,
            'paid_at': actual_paid_at_for_tx,
            'total_amount': total_paid_for_this_tx,
            'currency': currency,
            'items_count': len(items_in_payout),
            'items_details': items_in_payout 
        })
    payout_history_grouped.sort(key=lambda x: x['paid_at'] if x['paid_at'] else timezone.now(), reverse=True)

    # --- Earnings Stats ---
    now = timezone.now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = current_month_start - timedelta(microseconds=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    current_month_earnings_paid_sum = (
        ExpertEarning.objects.filter(expert=expert_profile, status=ExpertEarning.PAID, paid_at__gte=current_month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    ) + (
        ExpertBonus.objects.filter(expert=expert_profile, status=ExpertBonus.PAID, paid_at__gte=current_month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    )

    last_month_earnings_paid_sum = (
        ExpertEarning.objects.filter(expert=expert_profile, status=ExpertEarning.PAID, paid_at__gte=last_month_start, paid_at__lt=current_month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    ) + (
        ExpertBonus.objects.filter(expert=expert_profile, status=ExpertBonus.PAID, paid_at__gte=last_month_start, paid_at__lt=current_month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    )
    
    lifetime_paid_amount = sum(p['total_amount'] for p in payout_history_grouped)


    # --- Calculate Next Scheduled Payout Date ---
    today = timezone.now().date()
    days_until_friday = (4 - today.weekday() + 7) % 7 # 4 is Friday
    next_friday_date = today + timedelta(days=days_until_friday)
    
    payout_time_hour = 12 # Assume 12 PM server time for payout processing
    # If today is Friday and current time is past payout processing time, next payout is next week's Friday.
    if today.weekday() == 4 and timezone.now().time() >= timezone.datetime(1,1,1,payout_time_hour,0).time():
        next_friday_date = today + timedelta(days=7)
        
    next_payout_date_str = next_friday_date.strftime('%A, %B %d, %Y') + f" (around {payout_time_hour}:00 server time)"


    context = {
        'expert': expert_profile,
        'page_title': 'My Earnings & Payouts',
        'active_nav': 'earnings',

        'stripe_connected': stripe_connected,
        'stripe_account_details_summary': stripe_account_details_summary,
        'stripe_onboarding_needed': stripe_onboarding_needed,
        'stripe_payouts_ready_for_schedule': stripe_payouts_ready_for_schedule, # Use this in template
        'stripe_login_link_available': stripe_login_link_available,
        'stripe_account_issues': stripe_account_issues,

        'pending_payout_amount': pending_payout_amount,
        'total_lifetime_earnings': total_lifetime_earnings,
        'lifetime_paid_amount': lifetime_paid_amount,

        'pending_earnings_records': pending_earnings_records,
        'pending_bonuses_records': pending_bonuses_records,
        'payout_history_grouped': payout_history_grouped,

        'current_month_earnings_paid': current_month_earnings_paid_sum,
        'last_month_earnings_paid': last_month_earnings_paid_sum,
        
        'next_payout_date_str': next_payout_date_str,
    }
    return render(request, 'expert_marketplace/expert_earnings.html', context)









@login_required
def expert_stripe_connect_onboard_view(request):
    try:
        expert_profile = request.user.expert_profile
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    if not expert_profile.stripe_account_id:
        try:
            # Create a Stripe account for the expert if it doesn't exist
            account = stripe.Account.create(
                type='express', # or 'standard'
                email=expert_profile.email,
                business_type='individual', # Or 'company' based on your model
                individual={
                    'first_name': expert_profile.first_name,
                    'last_name': expert_profile.last_name,
                    'email': expert_profile.email,
                },
                # Add more details if available and required by Stripe for creation
                # capabilities={'card_payments': {'requested': True}, 'transfers': {'requested': True}},
                # business_profile={'url': settings.SITE_URL}, # Your platform's URL
                # tos_acceptance={'date': int(timezone.now().timestamp()), 'ip': request.META.get('REMOTE_ADDR')}, # If collecting ToS upfront
            )
            expert_profile.stripe_account_id = account.id
            expert_profile.save(update_fields=['stripe_account_id'])
            logger.info(f"Stripe Account {account.id} created for expert {expert_profile.id}")
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating account for expert {expert_profile.id}: {str(e)}")
            messages.error(request, f"Could not create Stripe account: {str(e)}")
            return redirect('expert_marketplace:expert_earnings')
        except Exception as e:
            logger.error(f"Generic error creating account for expert {expert_profile.id}: {str(e)}")
            messages.error(request, "An unexpected error occurred creating Stripe account.")
            return redirect('expert_marketplace:expert_earnings')


    try:
        account_link = stripe.AccountLink.create(
            account=expert_profile.stripe_account_id,
            refresh_url=request.build_absolute_uri(reverse('expert_marketplace:expert_stripe_connect_onboard')), # Re-trigger this view
            return_url=request.build_absolute_uri(reverse('expert_marketplace:expert_stripe_connect_return')),
            type='account_onboarding',
        )
        return redirect(account_link.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating account link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, f"Could not initiate Stripe connection: {str(e)}")
    except Exception as e:
        logger.error(f"Generic error creating account link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, "An unexpected error occurred initiating Stripe connection.")
    return redirect('expert_marketplace:expert_earnings')


@login_required
def expert_stripe_connect_return_view(request):
    try:
        expert_profile = request.user.expert_profile
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    if not expert_profile.stripe_account_id:
        messages.error(request, "Stripe account ID not found. Please try connecting again.")
        return redirect('expert_marketplace:expert_earnings')

    try:
        account = stripe.Account.retrieve(expert_profile.stripe_account_id)
        if account.details_submitted and account.payouts_enabled:
            messages.success(request, "Stripe account connected and verified successfully! Payouts are enabled.")
        elif account.details_submitted:
            messages.warning(request, "Stripe account details submitted. Verification may be pending. We will notify you once payouts are enabled.")
        else:
            messages.warning(request, "Stripe onboarding may not be complete. Please ensure all required information is provided in Stripe.")
        
        # Optionally update a local status field on expert_profile here
        # expert_profile.stripe_account_status = "connected" / "pending_verification"
        # expert_profile.save()

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error retrieving account status for expert {expert_profile.id} on return: {str(e)}")
        messages.error(request, f"Could not confirm Stripe connection status: {str(e)}")
    except Exception as e:
        logger.error(f"Generic error retrieving account status for expert {expert_profile.id} on return: {str(e)}")
        messages.error(request, "An unexpected error occurred confirming Stripe connection status.")
        
    return redirect('expert_marketplace:expert_earnings')


@login_required
def expert_stripe_login_link_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.stripe_account_id:
            messages.error(request, "Stripe account not connected. Cannot generate login link.")
            return redirect('expert_marketplace:expert_earnings')
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    try:
        login_link = stripe.Account.create_login_link(expert_profile.stripe_account_id)
        return redirect(login_link.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating login link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, f"Could not generate Stripe dashboard link: {str(e)}")
    except Exception as e:
        logger.error(f"Generic error creating login link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, "An unexpected error occurred generating Stripe dashboard link.")
    return redirect('expert_marketplace:expert_earnings')
    
    # Add logic to fetch and display earnings data here
    # For example, from an ExpertEarning model
    # earnings = ExpertEarning.objects.filter(expert=expert_profile).order_by('-created_at')
    earnings = [] # Placeholder

    context = {
        'expert': expert_profile,
        'earnings': earnings,
        'page_title': 'My Earnings',
        'active_nav': 'earnings'
    }
    # You'll need to create 'expert_marketplace/expert_earnings.html'
    return render(request, 'expert_marketplace/expert_earnings.html', context)


@login_required
def expert_stripe_connect_onboard_view(request):
    try:
        expert_profile = request.user.expert_profile
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    if not expert_profile.stripe_account_id:
        try:
            # Create a Stripe account for the expert if it doesn't exist
            account = stripe.Account.create(
                type='express', # or 'standard'
                email=expert_profile.email,
                business_type='individual', # Or 'company' based on your model
                individual={
                    'first_name': expert_profile.first_name,
                    'last_name': expert_profile.last_name,
                    'email': expert_profile.email,
                },
                # Add more details if available and required by Stripe for creation
                # capabilities={'card_payments': {'requested': True}, 'transfers': {'requested': True}},
                # business_profile={'url': settings.SITE_URL}, # Your platform's URL
                # tos_acceptance={'date': int(timezone.now().timestamp()), 'ip': request.META.get('REMOTE_ADDR')}, # If collecting ToS upfront
            )
            expert_profile.stripe_account_id = account.id
            expert_profile.save(update_fields=['stripe_account_id'])
            logger.info(f"Stripe Account {account.id} created for expert {expert_profile.id}")
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating account for expert {expert_profile.id}: {str(e)}")
            messages.error(request, f"Could not create Stripe account: {str(e)}")
            return redirect('expert_marketplace:expert_earnings')
        except Exception as e:
            logger.error(f"Generic error creating account for expert {expert_profile.id}: {str(e)}")
            messages.error(request, "An unexpected error occurred creating Stripe account.")
            return redirect('expert_marketplace:expert_earnings')


    try:
        account_link = stripe.AccountLink.create(
            account=expert_profile.stripe_account_id,
            refresh_url=request.build_absolute_uri(reverse('expert_marketplace:expert_stripe_connect_onboard')), # Re-trigger this view
            return_url=request.build_absolute_uri(reverse('expert_marketplace:expert_stripe_connect_return')),
            type='account_onboarding',
        )
        return redirect(account_link.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating account link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, f"Could not initiate Stripe connection: {str(e)}")
    except Exception as e:
        logger.error(f"Generic error creating account link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, "An unexpected error occurred initiating Stripe connection.")
    return redirect('expert_marketplace:expert_earnings')


@login_required
def expert_stripe_connect_return_view(request):
    try:
        expert_profile = request.user.expert_profile
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    if not expert_profile.stripe_account_id:
        messages.error(request, "Stripe account ID not found. Please try connecting again.")
        return redirect('expert_marketplace:expert_earnings')

    try:
        account = stripe.Account.retrieve(expert_profile.stripe_account_id)
        if account.details_submitted and account.payouts_enabled:
            messages.success(request, "Stripe account connected and verified successfully! Payouts are enabled.")
        elif account.details_submitted:
            messages.warning(request, "Stripe account details submitted. Verification may be pending. We will notify you once payouts are enabled.")
        else:
            messages.warning(request, "Stripe onboarding may not be complete. Please ensure all required information is provided in Stripe.")
        
        # Optionally update a local status field on expert_profile here
        # expert_profile.stripe_account_status = "connected" / "pending_verification"
        # expert_profile.save()

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error retrieving account status for expert {expert_profile.id} on return: {str(e)}")
        messages.error(request, f"Could not confirm Stripe connection status: {str(e)}")
    except Exception as e:
        logger.error(f"Generic error retrieving account status for expert {expert_profile.id} on return: {str(e)}")
        messages.error(request, "An unexpected error occurred confirming Stripe connection status.")
        
    return redirect('expert_marketplace:expert_earnings')


@login_required
def expert_stripe_login_link_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.stripe_account_id:
            messages.error(request, "Stripe account not connected. Cannot generate login link.")
            return redirect('expert_marketplace:expert_earnings')
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    try:
        login_link = stripe.Account.create_login_link(expert_profile.stripe_account_id)
        return redirect(login_link.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating login link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, f"Could not generate Stripe dashboard link: {str(e)}")
    except Exception as e:
        logger.error(f"Generic error creating login link for expert {expert_profile.id}: {str(e)}")
        messages.error(request, "An unexpected error occurred generating Stripe dashboard link.")
    return redirect('expert_marketplace:expert_earnings')


    

# expert_marketplace/views.py
# ... (other imports and views) ...

@login_required
def expert_support_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            auth_logout(request)
            return redirect('expert_marketplace:expert_login') # Ensure this URL name is correct
    except AttributeError:
        messages.error(request, "Access denied. This view is for active experts only.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login') # Ensure this URL name is correct
    except Expert.DoesNotExist:
        messages.error(request, "Expert profile not found. Please contact support.")
        auth_logout(request)
        return redirect('expert_marketplace:expert_login') # Ensure this URL name is correct

    # Add logic for a support contact form or displaying support information
    context = {
        'expert': expert_profile,
        'page_title': 'Support',
        'active_nav': 'support' # If you add it to the main nav
    }
    # You'll need to create 'expert_marketplace/expert_support.html'
    return render(request, 'expert_marketplace/expert_support.html', context)



@login_required
@require_POST # Ensure this is a POST request
def request_instant_payout_view(request):
    try:
        expert_profile = request.user.expert_profile
        if not expert_profile.is_active:
            messages.error(request, "Your expert account is inactive.")
            return redirect('expert_marketplace:expert_login')
    except (AttributeError, Expert.DoesNotExist):
        messages.error(request, "Access denied or expert profile not found.")
        return redirect('expert_marketplace:expert_login')

    if not expert_profile.stripe_account_id or not expert_profile.stripe_payouts_enabled(): # Assuming a method/property
        messages.error(request, "Your Stripe account is not connected or payouts are not enabled. Please check your Stripe settings.")
        return redirect('expert_marketplace:expert_earnings')

    pending_earnings_to_payout = ExpertEarning.objects.filter(
        expert=expert_profile, 
        status=ExpertEarning.PENDING,
        amount__gt=Decimal('0.00') # Only positive amounts
    )

    if not pending_earnings_to_payout.exists():
        messages.info(request, "You have no pending earnings eligible for an instant payout.")
        return redirect('expert_marketplace:expert_earnings')

    total_pending_gross = pending_earnings_to_payout.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    instant_payout_fee = Decimal('2.00')
    
    if total_pending_gross <= instant_payout_fee:
        messages.error(request, f"Your total pending earnings (£{total_pending_gross:.2f}) are not enough to cover the £{instant_payout_fee:.2f} instant payout fee.")
        return redirect('expert_marketplace:expert_earnings')

    logger.info(f"Expert {expert_profile.id} ({expert_profile.full_name}) requested instant payout for {pending_earnings_to_payout.count()} earnings, gross £{total_pending_gross:.2f}.")
    
    payout_result = process_expert_payouts(
        expert_profile=expert_profile,
        earnings_to_pay=list(pending_earnings_to_payout), # Pass as a list
        is_instant_request=True,
        payout_description=f"Expert-requested instant payout for {expert_profile.full_name}"
    )

    if payout_result.get('success'):
        messages.success(request, f"Instant payout request processed! {payout_result.get('message', '')}")
    else:
        messages.error(request, f"Instant payout request failed: {payout_result.get('error', 'An unknown error occurred.')}")
        
    return redirect('expert_marketplace:expert_earnings')