from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from custom_admin.models import AdminUser
import getpass

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates a new admin user for the custom admin panel'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Admin username')
        parser.add_argument('--email', type=str, help='Admin email')
        parser.add_argument('--role', type=str, default='admin',
                            choices=['super_admin', 'admin', 'moderator'],
                            help='Admin role (super_admin, admin, moderator)')
        parser.add_argument('--noinput', action='store_true',
                            help='Create user without interactive input')

    def handle(self, *args, **options):
        username = options.get('username')
        email = options.get('email')
        role = options.get('role')
        noinput = options.get('noinput')

        # If not provided as arguments, prompt for values
        if not noinput:
            if not username:
                username = input('Enter username: ')
            if not email:
                email = input('Enter email: ')
            if not role:
                role = input('Enter role (super_admin, admin, moderator) [default: admin]: ') or 'admin'

            password = getpass.getpass('Enter password: ')
            password_confirm = getpass.getpass('Confirm password: ')

            if password != password_confirm:
                self.stdout.write(self.style.ERROR('Passwords do not match'))
                return
        else:
            if not username or not email:
                self.stdout.write(self.style.ERROR('Username and email are required with --noinput'))
                return
            password = options.get('password')
            if not password:
                self.stdout.write(self.style.ERROR('Password is required with --noinput'))
                return

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'User with username "{username}" already exists'))
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f'User with email "{email}" already exists'))
            return

        # Create the user
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=True  # Give them staff status for potential Django admin access
            )

            # Create the admin profile
            AdminUser.objects.create(
                user=user,
                role=role,
                is_active=True
            )

            self.stdout.write(self.style.SUCCESS(f'Successfully created admin user "{username}" with role "{role}"'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating admin user: {str(e)}'))