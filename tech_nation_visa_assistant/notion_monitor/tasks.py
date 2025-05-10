from celery import shared_task
from .scraper import notion_scraper
from .models import Change
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from accounts.models import UserProfile
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

@shared_task
def check_notion_changes():
    """Check for changes in the Tech Nation Notion site"""
    logger.info("Starting Notion change detection task")

    # Scrape all pages and check for changes
    results = notion_scraper.scrape_all_pages()

    # If we found changes, notify users
    if results:
        logger.info(f"Found {len(results)} changes")
        for result in results:
            change = result['change']
            notify_users_of_change(change)
    else:
        logger.info("No changes detected")

    return len(results) if results else 0

def notify_users_of_change(change):
    """Notify users of a change in the Tech Nation guide"""
    # Get all users who want to be notified of guide changes
    users_to_notify = User.objects.filter(userprofile__notify_guide_changes=True)

    if not users_to_notify:
        logger.info("No users to notify")
        return

    # Prepare email content
    subject = f"Tech Nation Guide Update: {change.section}"

    # Different message for major vs minor changes
    if change.change_type == 'major':
        message = f"""
        Important Update to the Tech Nation Global Talent Visa Guide

        We've detected a significant change in the "{change.section}" section of the Tech Nation guide.

        Summary of changes:
        {change.description}

        This is a major update that may affect your application. We recommend reviewing your documents to ensure they align with the updated requirements.

        View the full details here: {settings.BASE_URL}/monitor/changes/{change.id}/

        Tech Nation Visa Assistant
        """
    else:
        message = f"""
        Tech Nation Global Talent Visa Guide Update

        We've detected a minor change in the "{change.section}" section of the Tech Nation guide.

        Summary of changes:
        {change.description}

        While this is a minor update, it's good to stay informed about any changes to the guide.

        View the full details here: {settings.BASE_URL}/monitor/changes/{change.id}/

        Tech Nation Visa Assistant
        """

    # Send emails to users
    for user in users_to_notify:
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            logger.info(f"Sent notification email to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send email to {user.email}: {e}")