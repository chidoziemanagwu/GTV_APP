from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def send_booking_confirmation_email(booking):
    """Send booking confirmation email to the client"""
    context = {
        'booking': booking,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    
    html_content = render_to_string('emails/expert/booking_confirmation.html', context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        'Your Consultation Booking Confirmation',
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [booking.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_expert_assignment_email(booking):
    """Send notification to expert about new assignment"""
    if not booking.expert:
        return
    
    context = {
        'booking': booking,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    
    html_content = render_to_string('emails/expert/expert_assignment.html', context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        'New Consultation Assignment',
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [booking.expert.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_payment_confirmation_email(booking):
    """Send payment confirmation email to client"""
    context = {
        'booking': booking,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
    }
    
    html_content = render_to_string('emails/expert/payment_confirmation.html', context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        'Payment Confirmation for Your Consultation',
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [booking.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_cancellation_email(booking):
    """Send cancellation email to client"""
    context = {
        'booking': booking,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        'refund_amount': booking.refund_amount,
    }
    
    html_content = render_to_string('emails/expert/booking_cancellation.html', context)
    text_content = strip_tags(html_content)
    
    email = EmailMultiAlternatives(
        'Your Consultation Booking Has Been Cancelled',
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [booking.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()

def send_admin_notification(subject, message, template_name=None, context=None):
    """Send notification to admin"""
    admin_email = settings.ADMIN_EMAIL
    
    if template_name and context:
        html_content = render_to_string(f'emails/expert/{template_name}.html', context)
        text_content = strip_tags(html_content)
    else:
        text_content = message
        html_content = f"<p>{message}</p>"
    
    email = EmailMultiAlternatives(
        subject,
        text_content,
        settings.DEFAULT_FROM_EMAIL,
        [admin_email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


def send_noshow_dispute_emails(dispute):
    """Send emails about a no-show dispute"""
    booking = dispute.booking
    
    # Email to expert with response link
    expert_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>No-Show Dispute - Action Required</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f9fafb;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
          <td align="center" style="padding: 20px 0;">
            <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
              <!-- Header -->
              <tr>
                <td style="background-color: #ef4444; padding: 20px; text-align: center;">
                  <h1 style="color: #ffffff; margin: 0; font-family: Arial, sans-serif;">No-Show Dispute - Action Required</h1>
                </td>
              </tr>
              
              <!-- Content -->
              <tr>
                <td style="padding: 30px 20px;">
                  <h2 style="color: #1f2937; margin-top: 0; font-family: Arial, sans-serif;">Client Has Reported You as No-Show</h2>
                  
                  <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">Hello {booking.expert.first_name},</p>
                  
                  <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">A client has reported that you did not attend the scheduled consultation (Booking #{booking.id}).</p>
                  
                  <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1f2937; font-family: Arial, sans-serif;">Booking Details</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Client:</strong> {booking.name}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Date:</strong> {booking.scheduled_date.strftime('%B %d, %Y')}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Time:</strong> {booking.scheduled_time}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Expertise:</strong> {booking.expertise_needed or "General Consultation"}</p>
                  </div>
                  
                  <div style="background-color: #fef2f2; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #b91c1c; font-family: Arial, sans-serif;">Client's Reason</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">{dispute.reason}</p>
                  </div>
                  
                  <div style="background-color: #eff6ff; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1e40af; font-family: Arial, sans-serif;">Action Required</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">You have 24 hours to respond to this dispute. If you don't respond, the dispute may be automatically upheld.</p>
                    
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">To respond, please click the button below:</p>
                    
                    <div style="text-align: center; margin: 25px 0;">
                      <a href="{settings.SITE_URL}/consultation/disputes/respond/{dispute.dispute_code}/" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-family: Arial, sans-serif; font-weight: bold; display: inline-block;">Respond to Dispute</a>
                    </div>
                    
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">If the button doesn't work, copy and paste this URL into your browser:</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px; word-break: break-all;">{settings.SITE_URL}/consultation/disputes/respond/{dispute.dispute_code}/</p>
                  </div>
                  
                  <div style="background-color: #fef3c7; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #92400e; font-family: Arial, sans-serif;">Important Notice</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">If this dispute is upheld, your payment for this booking will be withheld and the client will receive a refund.</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">Repeated no-shows may affect your status on our platform.</p>
                  </div>
                </td>
              </tr>
              
              <!-- Footer -->
              <tr>
                <td style="background-color: #f3f4f6; padding: 15px; text-align: center; font-family: Arial, sans-serif; font-size: 12px; color: #6b7280;">
                  <p>&copy; {timezone.now().year} Expert Consultation. All rights reserved.</p>
                  <p>This is an automated email, please do not reply.</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    
    expert_email = EmailMultiAlternatives(
        f"URGENT: No-Show Dispute - Booking #{booking.id}",
        strip_tags(expert_html),
        settings.DEFAULT_FROM_EMAIL,
        [booking.expert.email]
    )
    expert_email.attach_alternative(expert_html, "text/html")
    expert_email.send()
    
    # Email to admin
    admin_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>New No-Show Dispute</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f9fafb;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
          <td align="center" style="padding: 20px 0;">
            <table role="presentation" style="max-width: 600px; width: 100%; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
              <!-- Header -->
              <tr>
                <td style="background-color: #4f46e5; padding: 20px; text-align: center;">
                  <h1 style="color: #ffffff; margin: 0; font-family: Arial, sans-serif;">New No-Show Dispute</h1>
                </td>
              </tr>
              
              <!-- Content -->
              <tr>
                <td style="padding: 30px 20px;">
                  <h2 style="color: #1f2937; margin-top: 0; font-family: Arial, sans-serif;">Client Has Reported Expert No-Show</h2>
                  
                  <div style="background-color: #f3f4f6; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #1f2937; font-family: Arial, sans-serif;">Dispute Details</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Dispute ID:</strong> {dispute.id}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Booking ID:</strong> {booking.id}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Expert:</strong> {booking.expert.full_name}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Client:</strong> {booking.name}</p>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;"><strong>Date/Time:</strong> {booking.scheduled_date.strftime('%B %d, %Y')} at {booking.scheduled_time}</p>
                  </div>
                  
                  <div style="background-color: #fef2f2; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #b91c1c; font-family: Arial, sans-serif;">Client's Reason</h3>
                    <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 8px;">{dispute.reason}</p>
                  </div>
                  
                  <p style="font-family: Arial, sans-serif; color: #4b5563; margin-bottom: 15px;">The expert has been notified and has 24 hours to respond. After that, or after the expert responds, this dispute will require admin review.</p>
                  
                  <div style="text-align: center; margin: 25px 0;">
                    <a href="{settings.SITE_URL}/admin/expert_marketplace/noshowdispute/{dispute.id}/change/" style="background-color: #4f46e5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-family: Arial, sans-serif; font-weight: bold; display: inline-block;">View Dispute</a>
                  </div>
                </td>
              </tr>
              
              <!-- Footer -->
              <tr>
                <td style="background-color: #f3f4f6; padding: 15px; text-align: center; font-family: Arial, sans-serif; font-size: 12px; color: #6b7280;">
                  <p>&copy; {timezone.now().year} Expert Consultation. All rights reserved.</p>
                  <p>This is an automated email, please do not reply.</p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    
    admin_email = EmailMultiAlternatives(
        f"New No-Show Dispute - Booking #{booking.id}",
        strip_tags(admin_html),
        settings.DEFAULT_FROM_EMAIL,
        [settings.ADMIN_EMAIL]
    )
    admin_email.attach_alternative(admin_html, "text/html")
    admin_email.send()