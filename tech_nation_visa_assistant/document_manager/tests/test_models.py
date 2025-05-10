from django.test import TestCase
from django.contrib.auth import get_user_model
from document_manager.models import Document, Category, ChecklistItem

User = get_user_model()

class DocumentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        self.category = Category.objects.create(
            name='Personal Statement',
            description='Your personal statement document'
        )
        self.document = Document.objects.create(
            user=self.user,
            category=self.category,
            title='My Personal Statement',
            file_path='documents/personal_statement.pdf',
            status