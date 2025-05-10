# expert_marketplace/management/commands/setup_schedules.py
from django.core.management.base import BaseCommand
from django_q.tasks import schedule
from django_q.models import Schedule

class Command(BaseCommand):
    help = 'Sets up scheduled tasks for the application'

    def handle(self, *args, **kwargs):
        # Delete existing schedule if it exists
        Schedule.objects.filter(name='Check Auto Complete Bookings').delete()

        # Create new schedule
        schedule_obj = Schedule.objects.create(
            name='Check Auto Complete Bookings',
            func='expert_marketplace.tasks.process_auto_complete_bookings',
            schedule_type=Schedule.MINUTES,
            minutes=30
        )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created schedule: {schedule_obj.name}')
        )