from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def send_email(subject, template_name, context, recipient_email, from_email=None):
    """
    Generic function to send HTML email using Django's email system
    """
    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL

    try:
        # Render the HTML template
        html_content = render_to_string(template_name, context)
        text_content = strip_tags(html_content)

        # Create the email message
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[recipient_email]
        )

        # Attach the HTML version
        msg.attach_alternative(html_content, "text/html")

        # Send the email
        msg.send()
        logger.info(f"Email sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
        return False

def send_expert_application_confirmation(expert_data):
    """
    Send confirmation email to expert applicant
    """
    applicant_name = f"{expert_data.get('first_name')} {expert_data.get('last_name')}"
    recipient_email = expert_data.get('email')

    return send_email(
        subject="Your Expert Application Has Been Received",
        template_name="emails/expert/application_confirmation.html",
        context={
            'name': applicant_name,
        },
        recipient_email=recipient_email
    )

def send_expert_application_admin_notification(expert_data, admin_email, admin_url=None):
    """
    Send notification to admin about new expert application
    """
    if not admin_email:
        logger.error("Admin email is missing, cannot send notification")
        return False

    return send_email(
        subject="New Expert Application Submitted",
        template_name="emails/expert/admin_notification.html",
        context={
            'first_name': expert_data.get('first_name'),
            'last_name': expert_data.get('last_name'),
            'email': expert_data.get('email'),
            'phone_number': expert_data.get('phone_number'),
            'linkedin_profile': expert_data.get('linkedin_profile'),
            'company': expert_data.get('company'),
            'website': expert_data.get('website'),
            'specialization': expert_data.get('specialization'),
            'bio': expert_data.get('bio'),
            'hourly_rate': expert_data.get('hourly_rate'),
            'years_experience': expert_data.get('years_experience'),
            'availability': expert_data.get('availability'),
            'qualifications': expert_data.get('qualifications'),
            'certifications': expert_data.get('certifications'),
            'admin_url': admin_url,
        },
        recipient_email=admin_email
    )

def send_welcome_email(user):
    """
    Send welcome email to new users
    """
    return send_email(
        subject="Welcome to Tech Nation Visa Assistant",
        template_name="emails/welcome.html",
        context={
            'user': user,
        },
        recipient_email=user.email
    )

def send_password_reset_email(user, reset_url):
    """
    Send password reset email
    """
    return send_email(
        subject="Reset Your Password",
        template_name="emails/password_reset.html",
        context={
            'user': user,
            'reset_url': reset_url,
        },
        recipient_email=user.email
    )