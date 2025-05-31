# expert_marketplace/management/commands/create_initial_experts.py
from django.core.management.base import BaseCommand
from expert_marketplace.models import Expert, ExpertCategory
from django.utils import timezone

class Command(BaseCommand):
    help = 'Creates initial experts for the marketplace'

    def handle(self, *args, **kwargs):
        # Create categories
        categories = [
            {'name': 'Tech Nation Visa', 'description': 'Specialists in Tech Nation Global Talent Visa applications'},
            {'name': 'CV Optimization', 'description': 'Experts in optimizing CVs for tech roles'},
            {'name': 'Career Coaching', 'description': 'Professional career coaches for the tech industry'},
            {'name': 'Interview Preparation', 'description': 'Specialists in tech interview preparation'},
        ]

        created_categories = []
        for cat in categories:
            category, created = ExpertCategory.objects.get_or_create(
                name=cat['name'],
                defaults={'description': cat['description']}
            )
            created_categories.append(category)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created category: {category.name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Category already exists: {category.name}'))

        # Create experts
        experts = [
            {
                'name': 'Dr. Sarah Johnson',
                'email': 'sarah.johnson@example.com',
                'phone': '+44 7700 900123',
                'title': 'Tech Nation Visa Specialist',
                'bio': 'Dr. Johnson has helped over 200 applicants successfully obtain their Tech Nation Global Talent Visas. With a PhD in Immigration Law and 8 years of experience, she specializes in exceptional talent applications for tech professionals.',
                'hourly_rate': 150.00,
                'years_experience': 8,
                'rating': 4.9,
                'featured': True,
                'categories': [0, 2]  # Tech Nation Visa, Career Coaching
            },
            {
                'name': 'Michael Chen',
                'email': 'michael.chen@example.com',
                'phone': '+44 7700 900456',
                'title': 'CV & Personal Statement Expert',
                'bio': 'Former Tech Nation assessor with insider knowledge of what makes applications successful. Michael has reviewed over 500 applications and can help optimize your CV and personal statement to highlight your exceptional talent.',
                'hourly_rate': 125.00,
                'years_experience': 5,
                'rating': 4.8,
                'featured': True,
                'categories': [0, 1]  # Tech Nation Visa, CV Optimization
            },
            {
                'name': 'Priya Patel',
                'email': 'priya.patel@example.com',
                'phone': '+44 7700 900789',
                'title': 'Tech Career Coach',
                'bio': 'Priya is a certified career coach with expertise in the UK tech industry. She helps professionals navigate their career paths, prepare compelling applications, and develop strategies for professional growth.',
                'hourly_rate': 100.00,
                'years_experience': 6,
                'rating': 4.7,
                'featured': False,
                'categories': [2, 3]  # Career Coaching, Interview Preparation
            },
            {
                'name': 'James Wilson',
                'email': 'james.wilson@example.com',
                'phone': '+44 7700 900321',
                'title': 'Technical Interview Coach',
                'bio': 'Former hiring manager at Google and Amazon, James specializes in preparing candidates for technical interviews. He offers mock interviews, feedback, and strategies to showcase your technical expertise.',
                'hourly_rate': 135.00,
                'years_experience': 10,
                'rating': 4.9,
                'featured': False,
                'categories': [3, 2]  # Interview Preparation, Career Coaching
            },
        ]

        for expert_data in experts:
            # Check if expert already exists
            if Expert.objects.filter(email=expert_data['email']).exists():
                self.stdout.write(self.style.WARNING(f"Expert with email {expert_data['email']} already exists. Skipping."))
                continue

            # Create expert
            expert = Expert.objects.create(
                name=expert_data['name'],
                email=expert_data['email'],
                phone=expert_data['phone'],
                title=expert_data['title'],
                bio=expert_data['bio'],
                hourly_rate=expert_data['hourly_rate'],
                years_experience=expert_data['years_experience'],
                rating=expert_data['rating'],
                featured=expert_data['featured']
            )

            # Add categories
            for cat_index in expert_data['categories']:
                expert.categories.add(created_categories[cat_index])

            self.stdout.write(self.style.SUCCESS(f'Created expert: {expert.name}'))

        self.stdout.write(self.style.SUCCESS('Successfully created initial experts'))