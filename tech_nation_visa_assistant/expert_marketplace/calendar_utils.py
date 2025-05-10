from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import EmailMultiAlternatives
import google.oauth2.credentials
import googleapiclient.discovery
import datetime
import uuid
from decimal import Decimal

def create_calendar_event(booking):
    """Create a Google Calendar event with Google Meet link"""
    # This is a placeholder for your actual Google Calendar integration
    # You would need to implement OAuth2 authentication and use the Google Calendar API

    # For now, let's simulate creating a meeting link
    meeting_id = str(uuid.uuid4()).replace('-', '')
    google_meet_link = f"https://meet.google.com/{meeting_id}"

    # Save the meeting link to the booking
    booking.meeting_link = google_meet_link
    booking.save()

    return {
        'id': f'event_{booking.id}',
        'htmlLink': f'https://calendar.google.com/calendar/event?eid={meeting_id}',
        'hangoutLink': google_meet_link
    }

def send_booking_confirmation_email(booking):
    """Send confirmation email to user and expert with calendar details"""
    # Calculate deposit and remaining amounts
    total_price = booking.service.price
    deposit_amount = total_price * Decimal('0.5')  # 50% deposit
    remaining_amount = total_price - deposit_amount

    # User email
    subject = f'Booking Confirmed: {booking.service.name}'
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = booking.user.email

    html_content = render_to_string('emails/expert/booking_confirmed.html', {
        'booking': booking,
        'site_url': settings.SITE_URL,
        'deposit_amount': deposit_amount,
        'remaining_amount': remaining_amount
    })
    text_content = strip_tags(html_content)

    # Create email
    email = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
    email.attach_alternative(html_content, "text/html")
    email.send()

    # Expert email
    expert_subject = f'New Booking Confirmed: {booking.service.name}'
    expert_to_email = booking.service.expert.user.email

    expert_html_content = render_to_string('emails/expert/expert_booking_confirmed.html', {
        'booking': booking,
        'site_url': settings.SITE_URL,
        'deposit_amount': deposit_amount,
        'remaining_amount': remaining_amount
    })
    expert_text_content = strip_tags(expert_html_content)

    # Create email for expert
    expert_email = EmailMultiAlternatives(expert_subject, expert_text_content, from_email, [expert_to_email])
    expert_email.attach_alternative(expert_html_content, "text/html")
    expert_email.send()