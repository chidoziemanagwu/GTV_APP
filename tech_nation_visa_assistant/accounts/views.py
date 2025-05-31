from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User, UserProfile
from .forms import AssessmentForm, ProfileUpdateForm
from document_manager.models import Document  # Update this import
from referrals.models import ReferralSignup
from django.db.models import F
from accounts.email_utils import send_email, send_welcome_email  # If you're using the new anymail version
from django.http import HttpResponseRedirect

# Update these imports to use the models from expert_marketplace
from expert_marketplace.models import Booking as ExpertSession  # Use Booking instead of ExpertSession
from .models import AIConversation, User, UserProfile, Activity


from django.http import JsonResponse
from django.utils import timezone
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.conf import settings
# accounts/views.py
from allauth.account.views import LoginView, SignupView, PasswordResetView
from .utils import verify_recaptcha, is_disposable_email, rate_limit_signup
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError



# accounts/views.py
class CustomLoginView(LoginView):
    def form_valid(self, form):
        recaptcha_response = self.request.POST.get('g-recaptcha-response')
        if not verify_recaptcha(self.request):
            messages.error(self.request, "Security verification failed. Please try again.")
            return self.form_invalid(form)

        # Store the success URL before authentication
        success_url = self.get_success_url()
        response = super().form_valid(form)
        messages.success(self.request, "Successfully signed in! Welcome back.")
        return HttpResponseRedirect(success_url)

    def form_invalid(self, form):
        # Add error messages based on error type
        if '__all__' in form.errors:
            for error in form.errors['__all__']:
                messages.error(self.request, error)
        elif form.errors:
            messages.error(self.request, "Invalid login credentials. Please try again.")

        # Call parent's form_invalid
        return super().form_invalid(form)
    




    

class CustomPasswordResetView(PasswordResetView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            try:
                social_account = SocialAccount.objects.get(user=request.user)
                messages.error(
                    request,
                    "You signed up using Google. Please use Google Sign-In to access your account."
                )
                return redirect('accounts:dashboard')
            except SocialAccount.DoesNotExist:
                pass

        if request.method == "POST":
            email = request.POST.get("email")
            try:
                if email and SocialAccount.objects.filter(user__email=email).exists():
                    messages.error(
                        request,
                        "This email address is registered with Google. Please use Google Sign-In to access your account."
                    )
                    return redirect('account_login')
            except Exception as e:
                print(f"Error checking social account: {e}")

        return super().dispatch(request, *args, **kwargs)
    




class CustomSignupView(SignupView):
    def form_valid(self, form):
        # --- Anti-gaming: Rate limit by IP ---
        if not rate_limit_signup(self.request):
            form.add_error(None, "Too many signups from your IP. Please try again later.")
            messages.error(self.request, "Too many signups from your IP. Please try again later.")
            return self.form_invalid(form)

        # --- Anti-gaming: Block disposable emails ---
        email = form.cleaned_data.get('email')
        if is_disposable_email(email):
            form.add_error('email', "Disposable email addresses are not allowed.")
            messages.error(self.request, "Disposable email addresses are not allowed.")
            return self.form_invalid(form)

        # --- Security: Verify Turnstile/reCAPTCHA ---
        recaptcha_response = self.request.POST.get('g-recaptcha-response')
        if not verify_recaptcha(self.request):
            form.add_error(None, "Security verification failed. Please try again.")
            messages.error(self.request, "Security verification failed. Please try again.")
            return self.form_invalid(form)

        # --- Referral code (optional, if you want to auto-link on signup) ---
        referral_code = self.request.GET.get('ref')
        if referral_code:
            self.request.session['referral_code'] = referral_code  # Store for use after signup

        # --- Continue with normal signup process ---
        response = super().form_valid(form)

        # --- Only send welcome email for form signups (not social) ---
        if not hasattr(self.user, 'socialaccount_set') or not self.user.socialaccount_set.exists():
            send_email(
                subject="Welcome to Tech Nation Visa Assistant",
                template_name="emails/account/welcome.html",
                context={'user': self.user},
                recipient_email=self.user.email
            )

        # ... inside form_valid after user is created ...
        referral_code = self.request.session.pop('referral_code', None)
        if referral_code:
            from referrals.models import ReferralCode, ReferralSignup
            try:
                code_obj = ReferralCode.objects.get(code=referral_code)
                # Prevent self-referral
                if code_obj.user != self.user:
                    # Limit referrals per IP
                    ip = self.request.META.get('REMOTE_ADDR', '')
                    from django.utils import timezone
                    from datetime import timedelta
                    recent_referrals = ReferralSignup.objects.filter(
                        ip_address=ip,
                        timestamp__gte=timezone.now() - timedelta(days=1)
                    ).count()
                    if recent_referrals < 3:
                        # Optionally, block disposable emails for referred user
                        if not is_disposable_email(self.user.email):
                            ReferralSignup.objects.get_or_create(
                                referral_code=code_obj,
                                referred_user=self.user,
                                defaults={'ip_address': ip}
                            )
            except ReferralCode.DoesNotExist:
                pass  # Invalid code, ignore

        return response

    def form_invalid(self, form):
        # Add error messages based on error type
        if '__all__' in form.errors:
            for error in form.errors['__all__']:
                messages.error(self.request, error)
        elif form.errors:
            messages.error(self.request, "There was an error with your signup. Please check the form and try again.")
        return super().form_invalid(form)
    


        
def award_referral_points(user):
    """Award points to referrer when user becomes a paying customer"""
    try:
        # Get the referral signup for this user
        referral_signup = ReferralSignup.objects.filter(
            referred_user=user,
            points_awarded=False
        ).first()

        if referral_signup:
            # Get the referrer through the referral code
            referrer = referral_signup.referral_code.user

            # Award 3 points to referrer's profile
            referrer.profile.ai_points = F('ai_points') + 3
            referrer.profile.save()

            # Mark points as awarded
            referral_signup.points_awarded = True
            referral_signup.points_awarded_at = timezone.now()
            referral_signup.save()

            # Send notification email to referrer
            send_email(
                subject="You earned referral points!",
                template_name="emails/referrals/points_awarded.html",  # Updated path
                context={
                    'referrer': referrer,
                    'referred_email': user.email,
                    'points_earned': 3,
                    'total_points': referrer.profile.ai_points,
                },
                recipient_email=referrer.email
            )

            # Create activity for referrer
            Activity.objects.create(
                user=referrer,
                type='referral_reward',
                description=f'Earned 3 AI points from referral: {user.email}'
            )

    except Exception as e:
        print(f"Error awarding referral points: {e}")


def handle_payment_success(request, user):
    """Handle successful payment and award referral points"""
    # Your existing payment success logic...

    # Award referral points
    award_referral_points(user)

def home(request):
    """Landing page view"""
    return render(request, 'accounts/home.html')

@login_required
def dashboard(request):
    """User dashboard view"""
    # Get user profile or create if it doesn't exist
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Get user's current stage
    stage = request.user.application_stage

    # Get next steps based on user's stage
    next_steps = get_next_steps(request.user)

    # Check if user has a chosen personal statement
    has_chosen_personal_statement = Document.objects.filter(
        user=request.user,
        document_type='personal_statement',
        is_chosen=True
    ).exists()

    # Get document counts from document_status in UserProfile
    total_documents = len(profile.document_status.keys()) if profile.document_status else 0
    completed_documents = sum(1 for status in profile.document_status.values()
                            if status == 'completed') if profile.document_status else 0

    # Check if AI assistant has been used
    ai_assistant_used = False
    try:
        ai_assistant_used = AIConversation.objects.filter(user=request.user).exists()
    except:
        # AIConversation model might not exist or there's an error
        pass

    # Calculate progress percentage
    if has_chosen_personal_statement:
        # If user has chosen a personal statement, set progress to 100%
        progress_percentage = 100
        # Update application stage if needed
        if request.user.application_stage in ['assessment', 'document_preparation']:
            request.user.application_stage = 'submission_ready'
            request.user.save()
    else:
        # Normal progress calculation
        progress_percentage = 30  # Start with assessment done
        if total_documents > 0:
            doc_percentage = (completed_documents / total_documents) * 40
            progress_percentage += doc_percentage

        if ai_assistant_used:
            progress_percentage += 10

    # Round to nearest integer
    progress_percentage = min(100, int(round(progress_percentage)))

    # Calculate document preparation status
    if has_chosen_personal_statement:
        document_preparation_status = 'completed'
        document_progress = 100
    elif total_documents > 0 or ai_assistant_used:
        document_preparation_status = 'in_progress'
        document_progress = int((completed_documents / max(1, total_documents)) * 100)
    else:
        document_preparation_status = 'not_started'
        document_progress = 0

    # Get recent activities
    try:
        activities = Activity.objects.filter(user=request.user).order_by('-created_at')

        # Paginate activities
        paginator = Paginator(activities, 5)  # Show 5 activities per page
        page_number = request.GET.get('page')
        activities_page = paginator.get_page(page_number)
    except:
        # If Activity model doesn't exist yet or there's an error, use sample activities
        activities_page = []

        # Add sample activities if no real ones exist
        if not activities_page:
            # Get AI conversations
            try:
                ai_conversations = AIConversation.objects.filter(user=request.user).order_by('-created_at')[:3]
            except:
                ai_conversations = []

            # Create sample activities list
            sample_activities = []

            # Add assessment activity if completed
            if profile.assessment_completed:
                sample_activities.append({
                    'type': 'assessment',
                    'description': 'Assessment completed',
                    'created_at': profile.updated_at
                })

            # Add AI conversation activities
            for conv in ai_conversations:
                sample_activities.append({
                    'type': 'ai',
                    'description': f'AI Assistant query: "{conv.query[:30]}..."',
                    'created_at': conv.created_at
                })

            # Add document activity if any documents exist
            if profile.document_status:
                for doc_type, status in profile.document_status.items():
                    if status == 'completed':
                        doc_name = doc_type.replace('_', ' ').title()
                        sample_activities.append({
                            'type': 'document',
                            'description': f'{doc_name} completed',
                            'created_at': timezone.now() - timezone.timedelta(days=1)
                        })
                        break

            # Add personal statement chosen activity if applicable
            if has_chosen_personal_statement:
                sample_activities.append({
                    'type': 'document',
                    'description': 'Personal statement chosen for submission',
                    'created_at': timezone.now() - timezone.timedelta(hours=2)
                })

            # Sort by created_at
            activities_page = sorted(sample_activities, key=lambda x: x['created_at'], reverse=True)

    # Update next steps based on chosen personal statement
    if has_chosen_personal_statement and next_steps:
        # Filter out any steps related to creating personal statements
        next_steps = [step for step in next_steps if 'personal statement' not in step['title'].lower()]

        # Add submission step if not already present
        submission_step_exists = any('submit' in step['title'].lower() for step in next_steps)
        if not submission_step_exists:
            next_steps.insert(0, {
                'title': 'Submit Your Application',
                'description': 'Your documents are ready. Submit your application on the UK government website.',
                'priority': 'high'
            })

    context = {
        'profile': profile,
        'stage': stage,
        'next_steps': next_steps,
        'activities': activities_page,
        'now': timezone.now(),
        'total_documents': total_documents,
        'completed_documents': completed_documents,
        'progress_percentage': progress_percentage,
        'ai_assistant_used': ai_assistant_used,
        'has_chosen_personal_statement': has_chosen_personal_statement,
        'document_preparation_status': document_preparation_status,
        'document_progress': document_progress,
        'submission_ready': has_chosen_personal_statement,  # New variable for template
    }

    # Calculate referral points
    referral_points = 0
    try:
        from referrals.models import ReferralCode, ReferralSignup
        referral_code = ReferralCode.objects.filter(user=request.user).first()
        if referral_code:
            # Get referral stats
            referral_signups = referral_code.signups.all()
            paying_referrals = referral_signups.filter(points_awarded=True)

            # Calculate total points (3 per paying customer)
            referral_points = paying_referrals.count() * 3

            context.update({
                'referral_code': referral_code,
                'total_referrals': referral_signups.count(),
                'paying_referrals': paying_referrals.count(),
                'referral_points': referral_points,  # Add this explicitly for the template
                'total_points_earned': referral_points,  # Keep this for backward compatibility
                'paying_customers_count': paying_referrals.count(),
            })
        else:
            # Create a referral code if one doesn't exist
            referral_code = ReferralCode.objects.create(user=request.user)
            context.update({
                'referral_code': referral_code,
                'total_referrals': 0,
                'paying_referrals': 0,
                'referral_points': 0,  # Add this explicitly for the template
                'total_points_earned': 0,
                'paying_customers_count': 0,
            })
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error calculating referral points: {e}")
        # Set default values if there's an error
        context.update({
            'referral_points': 0,
            'total_points_earned': 0,
            'paying_customers_count': 0,
        })

    return render(request, 'accounts/dashboard.html', context)





    
    
    
    
    
    
    
def contact(request):
    if request.method == 'POST':
        # Verify Turnstile
        if not verify_recaptcha(request):
            messages.error(request, "Security verification failed. Please try again.")
            return render(request, 'accounts/contact.html')

        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')

        try:
            # Send notification email to admin
            admin_email = settings.ADMIN_EMAIL

            # Send to admin
            send_email(
                subject=f"Contact Form: {subject}",
                template_name="emails/contact/admin_notification.html",  # Updated path
                context={
                    'name': name,
                    'email': email,
                    'subject': subject,
                    'message': message,
                },
                recipient_email=admin_email
            )

            # Send confirmation to user
            send_email(
                subject="We've received your message",
                template_name="emails/contact/confirmation.html",  # Updated path
                context={
                    'name': name,
                },
                recipient_email=email
            )

            messages.success(request, 'Your message has been sent. We will get back to you soon!')
            return redirect('accounts:contact')
        except Exception as e:
            messages.error(request, f'There was an error sending your message: {str(e)}')

    return render(request, 'accounts/contact.html')







@login_required
def assessment(request):
    # Check if assessment is already completed
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if profile.assessment_completed:
        messages.info(request, "You have already completed the assessment.")
        return redirect('accounts:dashboard')

    if request.method == 'POST':
        form = AssessmentForm(request.POST)
        if form.is_valid():
            try:
                # Get the form data
                user = request.user

                # Update user fields from form data
                user.background_type = form.cleaned_data.get('background_type')
                user.years_of_experience = form.cleaned_data.get('years_experience')

                # Determine visa path based on years of experience
                if form.cleaned_data.get('years_experience') in ['5_to_10', 'more_than_10']:
                    user.visa_path = 'talent'
                else:
                    user.visa_path = 'promise'

                user.save()

                # Update profile with specializations and mark assessment as completed
                profile.tech_specializations = form.cleaned_data.get('tech_specializations', [])
                profile.assessment_completed = True
                profile.save()

                messages.success(
                    request,
                    f'Assessment completed! Based on your experience, we recommend the Global '
                    f'{"Talent" if user.visa_path == "talent" else "Promise"} visa path.'
                )
                return redirect('accounts:dashboard')
            except Exception as e:
                messages.error(request, f"An error occurred: {str(e)}")
        else:
            # Form is invalid, errors will be displayed in the template
            pass
    else:
        form = AssessmentForm()  # No need for initial email here

    return render(request, 'accounts/assessment.html', {
        'form': form,
        'profile': profile
    })
# accounts/views.py

@login_required
def profile(request):
    """User profile view and edit"""
    profile = request.user.profile

    # Get user points
    try:
        from document_manager.models import UserPoints
        user_points = UserPoints.objects.get(user=request.user)
    except:
        # If UserPoints model doesn't exist or user doesn't have points
        user_points = None

    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            # Get the cleaned data
            current_country = form.cleaned_data.get('current_country')
            target_uk_region = form.cleaned_data.get('target_uk_region')
            tech_specializations = form.cleaned_data.get('tech_specializations', [])

            # Update profile
            profile.current_country = current_country
            profile.target_uk_region = target_uk_region
            profile.tech_specializations = tech_specializations
            profile.save()

            messages.success(request, 'Your profile has been updated!')
            return redirect('accounts:profile')
    else:
        # Initialize form with current values
        initial_data = {
            'current_country': profile.current_country,
            'target_uk_region': profile.target_uk_region,
            'tech_specializations': profile.tech_specializations
        }
        form = ProfileUpdateForm(instance=profile, initial=initial_data)

    context = {
        'form': form,
        'profile': profile,
        'remaining_queries': profile.ai_queries_limit - profile.ai_queries_used if hasattr(profile, 'ai_queries_used') else 0,
        'user_points': user_points.balance if user_points else 0,
    }

    return render(request, 'accounts/profile.html', context)










@login_required
def visa_path_selection(request):
    """Allow user to select visa path"""
    if request.method == 'POST':
        path = request.POST.get('visa_path')
        if path in ['talent', 'promise']:
            request.user.visa_path = path
            request.user.save()
            messages.success(request, f'You have selected the Exceptional {path.title()} path.')
            return redirect('dashboard')

    return render(request, 'accounts/visa_path_selection.html')




@login_required
def digital_tech_path(request):
    # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Ensure documents_completed is properly set
    if created or profile.document_status:
        profile.documents_completed = profile.check_documents_completed()
        profile.save()

    # Calculate progress
    progress = profile.get_progress_percentage()

    context = {
        'user': request.user,
        'profile': profile,
        'progress': progress,
        'steps': {
            'assessment': {
                'completed': profile.assessment_completed,
                'available': True,
                'url': 'accounts:assessment'
            },
            'documents': {
                'completed': profile.documents_completed,
                'available': profile.assessment_completed,
                'url': 'document_manager:checklist'
            },
            'expert_review': {
                'completed': profile.expert_review_completed,
                'available': profile.documents_completed,
                'url': 'expert_marketplace:expert_list'
            },
            'submission': {
                'completed': profile.application_submitted,
                'available': profile.expert_review_completed,
                'url': 'accounts:final_submission'
            }
        }
    }

    return render(request, 'accounts/digital_tech_path.html', context)





def get_next_steps(user):
    """Generate recommended next steps based on user's current stage"""
    stage = user.application_stage
    steps = []

    if stage == 'assessment':
        if not user.profile.assessment_completed:
            steps.append({
                'title': 'Complete Initial Assessment',
                'description': 'Answer questions about your background to determine eligibility',
                'url': '/assessment/',
                'priority': 'high'
            })
        if user.visa_path == 'undecided':
            steps.append({
                'title': 'Select Visa Path',
                'description': 'Choose between Exceptional Talent and Exceptional Promise',
                'url': '/visa-path-selection/',
                'priority': 'high'
            })

    elif stage == 'preparation':
        # Add document preparation steps
        steps.append({
            'title': 'Create Personal Statement',
            'description': 'Write your 1000-word personal statement',
            'url': '/documents/personal-statement/',
            'priority': 'high'
        })
        steps.append({
            'title': 'Prepare CV',
            'description': 'Create or update your CV for the application',
            'url': '/documents/cv/',
            'priority': 'high'
        })
        steps.append({
            'title': 'Gather Evidence Documents',
            'description': 'Collect documents for your selected criteria',
            'url': '/documents/evidence/',
            'priority': 'medium'
        })

    # Add more stage-specific steps as needed

    return steps


@login_required
def update_notifications(request):
    if request.method == 'POST':
        user = request.user
        user.notify_guide_changes = request.POST.get('notify_guide_changes') == 'on'
        user.notify_app_updates = request.POST.get('notify_app_updates') == 'on'
        user.save()
        messages.success(request, 'Notification preferences updated successfully.')
    return redirect('accounts:profile')

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        messages.success(request, 'Your account has been deleted.')
        return redirect('home')
    return render(request, 'accounts/delete_account.html')




@login_required
def document_checklist(request):
    """Document checklist view"""
    profile = request.user.profile

    if not profile.assessment_completed:
        messages.warning(request, 'Please complete the assessment first.')
        return redirect('assessment')

    # Get documents based on visa path
    required_documents = get_required_documents(request.user.visa_path)
    uploaded_documents = request.user.documents.all()

    # Calculate completion percentage
    total_docs = len(required_documents)
    completed_docs = sum(1 for doc in required_documents
                        if doc['name'] in profile.document_status
                        and profile.document_status[doc['name']] == 'completed')

    completion_percentage = (completed_docs / total_docs * 100) if total_docs > 0 else 0

    # Update documents_completed status
    profile.documents_completed = profile.check_documents_completed()
    profile.save()

    context = {
        'required_documents': required_documents,
        'uploaded_documents': uploaded_documents,
        'completion_percentage': completion_percentage,
        'profile': profile,
        'document_status': profile.document_status
    }
    return render(request, 'document_manager/document_list.html', context)






def get_required_documents(visa_path):
    """Helper function to get required documents based on visa path"""
    common_documents = [
        {
            'name': 'personal_statement',
            'title': 'Personal Statement',
            'description': 'A 1000-word statement describing your achievements and expertise',
            'required': True
        },
        {
            'name': 'cv',
            'title': 'Curriculum Vitae',
            'description': 'Your detailed CV following Tech Nation guidelines',
            'required': True
        }
    ]

    talent_documents = [
        {
            'name': 'evidence_significant_impact',
            'title': 'Evidence of Significant Impact',
            'description': 'Documents showing your significant impact in the digital technology sector',
            'required': True
        }
    ]

    promise_documents = [
        {
            'name': 'evidence_potential',
            'title': 'Evidence of Potential',
            'description': 'Documents showing your potential to be a leader in digital technology',
            'required': True
        }
    ]

    documents = common_documents + (talent_documents if visa_path == 'talent' else promise_documents)
    return documents

@login_required
def expert_marketplace(request):
    """Expert marketplace view"""
    # Get available experts
    experts = Expert.objects.filter(is_available=True)
    
    # Get user's booked sessions
    booked_sessions = ExpertSession.objects.filter(user=request.user)

    context = {
        'experts': experts,
        'booked_sessions': booked_sessions,
        'profile': request.user.profile
    }
    return render(request, 'accounts/expert_marketplace.html', context)

@login_required
def final_submission(request):
    """Final submission view"""
    profile = request.user.profile

    # Check if all requirements are met
    if not all([
        profile.assessment_completed,
        profile.documents_completed,
        profile.expert_review_completed
    ]):
        messages.warning(request, 'Please complete all required steps before final submission.')
        return redirect('digital_tech_path')

    if request.method == 'POST':
        # Handle final submission
        try:
            # Update application status
            profile.application_submitted = True
            profile.submission_date = timezone.now()
            profile.save()

            # Send confirmation email
            send_submission_confirmation(request.user)

            messages.success(request, 'Your application has been successfully submitted!')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, 'There was an error submitting your application. Please try again.')
            return redirect('final_submission')

    context = {
        'profile': profile,
        'documents': request.user.documents.all(),
        'expert_reviews': request.user.expert_reviews.all()
    }
    return render(request, 'accounts/final_submission.html', context)



def process_ai_query(query):
    """Helper function to process AI queries"""
    # Implement your AI processing logic here
    # This could involve calling OpenAI API or other AI services
    pass

def send_submission_confirmation(user):
    """Helper function to send submission confirmation email"""
    subject = 'Application Submission Confirmation'
    message = f"""
    Dear {user.get_full_name()},

    Your Tech Nation Global Talent Visa application has been successfully submitted.
    
    Application Details:
    - Submission Date: {user.profile.submission_date}
    - Application Type: Exceptional {user.visa_path.title()}
    - Reference Number: {generate_reference_number(user)}

    Next Steps:
    1. Tech Nation will review your application
    2. You will receive a decision within 8 weeks
    3. Keep monitoring your email for updates

    If you have any questions, please don't hesitate to contact us.

    Best regards,
    Tech Nation Visa Assistant Team
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )

def generate_reference_number(user):
    """Helper function to generate unique reference number"""
    timestamp = timezone.now().strftime('%Y%m%d%H%M')
    user_id = str(user.id).zfill(6)
    return f'TN{timestamp}{user_id}'






def terms_privacy(request):
    return render(request, 'legal/terms_privacy.html')