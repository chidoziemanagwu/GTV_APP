# expert_marketplace/schedulers.py
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.utils import timezone
from datetime import timedelta
from .tasks import process_booking_auto_complete
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
scheduler.add_jobstore(DjangoJobStore(), "default")

def schedule_booking_completion(booking_id):
    """
    Schedule a booking to be auto-completed after 1 minute (for testing)
    """
    job_id = f"complete_booking_{booking_id}"

    try:
        # Remove any existing job for this booking
        scheduler.remove_job(job_id, jobstore='default')
    except:
        pass

    # Schedule new job to run in 1 minute (for testing)
    scheduler.add_job(
        process_booking_auto_complete,
        'date',
        run_date=timezone.now() + timedelta(minutes=1),  # Changed to 1 minute for testing
        args=[booking_id],
        id=job_id,
        replace_existing=True,
        jobstore='default'
    )
    logger.info(f"Scheduled auto-completion for booking {booking_id}")

def start():
    try:
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Error starting scheduler: {str(e)}")