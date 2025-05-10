# expert_marketplace/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils.html import strip_tags
from .models import Booking
from .forms import ConsultationBookingForm

def book_consultation(request):
    if request.method == 'POST':
        form = ConsultationBookingForm(request.POST)
        if form.is_valid():
            booking = form.save()

            # Send confirmation email
            context = {
                'booking': booking,
                'site_url': settings.SITE_URL,
                'consultation_fee': '100',
                'consultation_duration': '30',
            }

            # Email to client
            html_content = render_to_string('emails/expert/booking_confirmation.html', context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                'Consultation Booking Confirmation',
                text_content,
                settings.DEFAULT_FROM_EMAIL,
                [booking.email]
            )
            email.attach_alternative(html_content, "text/html")
            email.send()

            # Email to admin
            admin_html_content = render_to_string('emails/expert/admin_booking_notification.html', context)
            admin_text_content = strip_tags(admin_html_content)

            admin_email = EmailMultiAlternatives(
                'New Consultation Booking',
                admin_text_content,
                settings.DEFAULT_FROM_EMAIL,
                [settings.ADMIN_EMAIL]  # Make sure to set ADMIN_EMAIL in settings.py
            )
            admin_email.attach_alternative(admin_html_content, "text/html")
            admin_email.send()

            messages.success(request, "Your consultation request has been received. We'll contact you shortly with next steps.")
            return redirect('expert_marketplace:consultation_confirmation')
    else:
        form = ConsultationBookingForm()

    return render(request, 'expert_marketplace/book_consultation.html', {
        'form': form,
        'consultation_fee': '100',
        'consultation_duration': '30',
    })

def consultation_confirmation(request):
    return render(request, 'expert_marketplace/consultation_confirmation.html')