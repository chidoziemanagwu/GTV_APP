from django.test import TestCase
from django.contrib.auth import get_user_model
from accounts.models import UserProfile

User = get_user_model()

class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            application_stage='preparing',
            specialization='technical'
        )

    def test_profile_creation(self):
        """Test that a profile can be created"""
        self.assertEqual(self.profile.user.username, 'testuser')
        self.assertEqual(self.profile.application_stage, 'preparing')
        self.assertEqual(self.profile.specialization, 'technical')

    def test_profile_str(self):
        """Test the string representation of a profile"""
        self.assertEqual(str(self.profile), 'test@example.com Profile')

    def test_get_application_stage_display(self):
        """Test the display value of application_stage"""
        self.assertEqual(
            self.profile.get_application_stage_display(),
            'Preparing Application'
        )

    def test_get_specialization_display(self):
        """Test the display value of specialization"""
        self.assertEqual(
            self.profile.get_specialization_display(),
            'Technical'
        )