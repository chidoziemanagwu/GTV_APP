# expert_marketplace/backends.py

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from .models import Expert # Ensure this is the correct path to your Expert model
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)
UserModel = get_user_model() # This is typically accounts.User

class ExpertAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Django 5+ might pass email in kwargs if username_field is email.
        # We prioritize the 'username' parameter as it's conventionally used for the primary identifier.
        login_identifier = username
        if login_identifier is None:
            login_identifier = kwargs.get('email') # Fallback for 'email' in kwargs
            if login_identifier is None: # Still None, try UserModel's email field name from kwargs
                 login_identifier = kwargs.get(UserModel.EMAIL_FIELD) # UserModel.EMAIL_FIELD is usually 'email'

        if not login_identifier:
            logger.debug("ExpertAuthBackend: No username/email identifier provided for authentication.")
            return None

        try:
            expert = Expert.objects.get(email__iexact=login_identifier)
            logger.info(f"ExpertAuthBackend: Attempting to authenticate expert with email: {login_identifier} (Expert ID: {expert.id})")
        except Expert.DoesNotExist:
            logger.info(f"ExpertAuthBackend: No Expert found with email: {login_identifier}")
            return None

        if expert.check_password(password) and expert.is_active:
            logger.info(f"ExpertAuthBackend: Credentials valid for Expert ID {expert.id} ({expert.email}).")
            
            user_account = expert.user # This is the OneToOneField to accounts.User
            expert_needs_save = False

            if not user_account:
                logger.info(f"ExpertAuthBackend: Expert ID {expert.id} not yet linked to a UserModel. Attempting to find/create.")
                try:
                    # Use get_or_create to find or create the associated UserModel
                    user_account, created = UserModel.objects.get_or_create(
                        email__iexact=expert.email, # Match by email case-insensitively
                        defaults={
                            # UserModel.USERNAME_FIELD is usually 'username'.
                            # Ensure this default username is unique if your UserModel requires it.
                            # Using a normalized version of the email is a common strategy.
                            UserModel.USERNAME_FIELD: expert.email.lower(),
                            'first_name': expert.first_name,
                            'last_name': expert.last_name,
                            # Add other necessary defaults for your UserModel here
                            # 'is_staff': False,
                            # 'is_superuser': False,
                        }
                    )
                    if created:
                        user_account.set_unusable_password() # Expert uses Expert model password
                        user_account.save() # Save the newly created user with defaults
                        logger.info(f"ExpertAuthBackend: Created new UserModel (ID: {user_account.id}, Email: {user_account.email}) for Expert ID {expert.id}.")
                    else:
                        logger.info(f"ExpertAuthBackend: Found existing UserModel (ID: {user_account.id}, Email: {user_account.email}) for Expert ID {expert.id}.")
                    
                    expert.user = user_account
                    expert_needs_save = True # Mark expert for saving due to new user link
                
                except Exception as e: # Catch potential errors during get_or_create or save
                    logger.error(f"ExpertAuthBackend: Error during UserModel get_or_create for Expert ID {expert.id} (Email: {expert.email}): {e}", exc_info=True)
                    return None # Abort authentication if user linking fails critically

            # Ensure the linked/found user_account is active
            if not user_account or not user_account.is_active:
                logger.warning(f"ExpertAuthBackend: Linked UserModel for Expert ID {expert.id} is missing or not active. Login denied.")
                return None

            # Update last_login on the Expert model
            expert.last_login = timezone.now()
            expert_needs_save = True

            if expert_needs_save:
                try:
                    update_fields = ['last_login']
                    if expert.user_id: # Check if user was set or already existed
                        update_fields.append('user')
                    expert.save(update_fields=update_fields)
                    logger.info(f"ExpertAuthBackend: Updated last_login (and user link if changed) for Expert ID {expert.id}.")
                except Exception as e:
                    logger.error(f"ExpertAuthBackend: Error saving Expert ID {expert.id} after updating last_login/user: {e}", exc_info=True)
                    # Decide if login should proceed. For now, let it if user_account is valid.

            # Attach custom attributes to the user_account instance for this request session
            # These are not saved to the UserModel database columns unless UserModel has these fields
            user_account.is_expert_user = True  # Flag to identify this user type in templates/views
            user_account.expert_profile = expert # Provide easy access to the full Expert profile

            logger.info(f"ExpertAuthBackend: Authenticated Expert ID {expert.id} as UserModel {user_account.email} (ID: {user_account.id}).")
            return user_account # Return the accounts.User instance

        else:
            if not expert.is_active:
                logger.warning(f"ExpertAuthBackend: Authentication failed for Expert {login_identifier} (Expert ID: {expert.id}) - account is not active.")
            else:
                logger.warning(f"ExpertAuthBackend: Authentication failed for Expert {login_identifier} (Expert ID: {expert.id}) - password incorrect.")
            return None

    def get_user(self, user_id):
        # This method is used by Django to retrieve the user object from the session
        try:
            user = UserModel.objects.get(pk=user_id)
            # Try to re-attach expert profile if this user is indeed an expert.
            # This makes request.user.expert_profile available in subsequent requests.
            try:
                # Assuming Expert.user (OneToOneField) is the definitive link
                expert_profile = Expert.objects.get(user_id=user.id)
                user.is_expert_user = True
                user.expert_profile = expert_profile
            except Expert.DoesNotExist:
                # This case should be rare if an expert user always has an expert_profile linked
                # but good to handle defensively.
                user.is_expert_user = False
                user.expert_profile = None
            return user
        except UserModel.DoesNotExist:
            logger.debug(f"ExpertAuthBackend: get_user - No UserModel found with ID: {user_id}")
            return None