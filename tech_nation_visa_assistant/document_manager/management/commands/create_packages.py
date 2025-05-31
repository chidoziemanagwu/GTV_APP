from django.core.management.base import BaseCommand
from document_manager.models import PointsPackage

class Command(BaseCommand):
    help = 'Creates default points packages'

    def handle(self, *args, **kwargs):
        packages = [
            {
                'name': 'Starter',
                'points': 10,
                'price': 7.99,
                'description': 'Generate 3 personal statements or analyze 10 CVs. Valid for 30 days.'
            },
            {
                'name': 'Standard',
                'points': 30,
                'price': 16.99,
                'description': 'Generate 10 personal statements or analyze 30 CVs. Valid for 60 days.'
            },
            {
                'name': 'Pro',
                'points': 100,
                'price': 39.99,
                'description': 'Generate unlimited personal statements and analyze unlimited CVs. Valid for 90 days.'
            }
        ]

        created_count = 0
        for package_data in packages:
            _, created = PointsPackage.objects.get_or_create(
                name=package_data['name'],
                defaults={
                    'points': package_data['points'],
                    'price': package_data['price'],
                    'description': package_data['description'],
                    'is_active': True
                }
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} packages')
        )