from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from expert_marketplace.models import Expert # Make sure this import path is correct for your Expert model
from django.db import transaction

UserModel = get_user_model()

class Command(BaseCommand):
    help = 'Finds Expert records with no linked User and attempts to link or create a User for them.'

    def handle(self, *args, **options):
        unlinked_experts = Expert.objects.filter(user__isnull=True)
        fixed_count = 0
        created_user_count = 0
        already_linked_count = 0 # Should be 0 if filter is correct, but good for sanity check
        error_count = 0

        if not unlinked_experts.exists():
            self.stdout.write(self.style.SUCCESS('No unlinked Expert records found.'))
            return

        self.stdout.write(f"Found {unlinked_experts.count()} unlinked Expert records. Attempting to fix...")

        for expert in unlinked_experts:
            if expert.user: # Double check, though filter should handle this
                self.stdout.write(self.style.NOTICE(f"Expert ID {expert.id} ({expert.email}) is already linked. Skipping."))
                already_linked_count +=1
                continue

            self.stdout.write(f"Processing Expert ID {expert.id} (Email: {expert.email})...")
            
            try:
                with transaction.atomic(): # Ensure operations are atomic for each expert
                    user_account = None
                    try:
                        # Attempt to find an existing user by the expert's email
                        user_account = UserModel.objects.get(email__iexact=expert.email)
                        self.stdout.write(self.style.SUCCESS(f"  Found existing User: {user_account.email} (ID: {user_account.id})"))
                    
                    except UserModel.DoesNotExist:
                        self.stdout.write(self.style.WARNING(f"  No User found with email {expert.email}. Creating a new User."))
                        # Create a new User
                        user_account = UserModel.objects.create_user(
                            email=expert.email,
                            first_name=expert.first_name,
                            last_name=expert.last_name
                            # password=None # create_user sets an unusable password if None
                                          # This is generally fine if Expert.password is the primary login method
                        )
                        # If you want to set a specific password for the UserModel (e.g., sync with Expert's password)
                        # you would need access to the raw password here, which is not ideal.
                        # Sticking to unusable password for UserModel is safer for dual login.
                        user_account.save()
                        created_user_count += 1
                        self.stdout.write(self.style.SUCCESS(f"  Created new User: {user_account.email} (ID: {user_account.id})"))

                    except UserModel.MultipleObjectsReturned:
                        self.stderr.write(self.style.ERROR(f"  CRITICAL ERROR: Multiple Users found with email {expert.email} for Expert ID {expert.id}. Manual intervention required. Skipping."))
                        error_count += 1
                        continue # Skip this expert

                    if user_account:
                        expert.user = user_account
                        expert.save(update_fields=['user'])
                        fixed_count += 1
                        self.stdout.write(self.style.SUCCESS(f"  Successfully linked Expert ID {expert.id} to User {user_account.email}."))
                    else:
                        # This case should ideally not be reached if logic above is correct
                        self.stderr.write(self.style.ERROR(f"  Failed to obtain or create a user for Expert ID {expert.id}. This is unexpected."))
                        error_count += 1
                        
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  An unexpected error occurred while processing Expert ID {expert.id}: {e}"))
                error_count += 1

        self.stdout.write(self.style.SUCCESS("\n--- Summary ---"))
        self.stdout.write(f"Successfully linked/fixed experts: {fixed_count}")
        self.stdout.write(f"New Users created: {created_user_count}")
        if already_linked_count > 0:
             self.stdout.write(f"Experts already linked (skipped): {already_linked_count}")
        if error_count > 0:
            self.stderr.write(self.style.ERROR(f"Experts with errors (manual intervention needed): {error_count}"))
        else:
            self.stdout.write(self.style.SUCCESS("No errors encountered."))