from django.db.models import Q
from .models import Document

def calculate_application_progress(user):
    """Calculate the user's application progress based on completed steps"""
    total_steps = 4  # Adjusted to match the 4 steps in your dashboard
    completed_steps = 0
    progress_details = {}

    # Step 1: Check if user has a chosen personal statement
    has_chosen_personal_statement = Document.objects.filter(
        user=user,
        document_type='personal_statement',
        is_chosen=True
    ).exists()

    if has_chosen_personal_statement:
        completed_steps += 1
        progress_details['personal_statement'] = True
    else:
        progress_details['personal_statement'] = False

    # Step 2: Check for CV
    has_cv = Document.objects.filter(
        user=user,
        document_type='cv',
        status='completed'
    ).exists()

    if has_cv:
        completed_steps += 1
        progress_details['cv'] = True
    else:
        progress_details['cv'] = False

    # Step 3: Check for mandatory evidence documents
    # Get count of mandatory criteria
    mandatory_criteria_count = user.documents.filter(
        related_criteria__criteria_type='mandatory',
        document_type='evidence'
    ).values('related_criteria').distinct().count()

    # Get count of completed mandatory evidence documents
    completed_mandatory_count = user.documents.filter(
        related_criteria__criteria_type='mandatory',
        document_type='evidence',
        status='completed'
    ).values('related_criteria').distinct().count()

    if mandatory_criteria_count > 0 and completed_mandatory_count >= mandatory_criteria_count:
        completed_steps += 1
        progress_details['mandatory_evidence'] = True
    else:
        progress_details['mandatory_evidence'] = False

    # Step 4: Check for recommendation letters
    has_recommendation = Document.objects.filter(
        user=user,
        document_type='recommendation',
        status='completed'
    ).exists()

    if has_recommendation:
        completed_steps += 1
        progress_details['recommendation'] = True
    else:
        progress_details['recommendation'] = False

    # Calculate percentage
    progress_percentage = int((completed_steps / total_steps) * 100)

    return {
        'percentage': progress_percentage,
        'completed_steps': completed_steps,
        'total_steps': total_steps,
        'details': progress_details
    }

def get_document_status_counts(user):
    """Get counts of documents by status for a user"""
    return {
        'total': Document.objects.filter(user=user).count(),
        'completed': Document.objects.filter(user=user, status='completed').count(),
        'draft': Document.objects.filter(user=user, status='draft').count(),
        'in_progress': Document.objects.filter(user=user, status='in_progress').count(),
        'reviewing': Document.objects.filter(user=user, status='reviewing').count(),
        'not_started': Document.objects.filter(user=user, status='not_started').count(),
        'archived': Document.objects.filter(user=user, status='archived').count(),
    }

def get_document_type_counts(user):
    """Get counts of documents by type for a user"""
    return {
        'personal_statement': Document.objects.filter(user=user, document_type='personal_statement').count(),
        'cv': Document.objects.filter(user=user, document_type='cv').count(),
        'evidence': Document.objects.filter(user=user, document_type='evidence').count(),
        'recommendation': Document.objects.filter(user=user, document_type='recommendation').count(),
        'other': Document.objects.filter(user=user, document_type='other').count(),
    }

def get_chosen_documents(user):
    """Get all documents marked as chosen for a user"""
    return Document.objects.filter(user=user, is_chosen=True)

def get_recent_documents(user, limit=5):
    """Get the most recently updated documents for a user"""
    return Document.objects.filter(user=user).order_by('-updated_at')[:limit]

def search_documents(user, query):
    """Search for documents by title or content"""
    return Document.objects.filter(
        user=user
    ).filter(
        Q(title__icontains=query) | Q(content__icontains=query)
    ).order_by('-updated_at')

def get_document_completion_percentage(user):
    """Calculate the percentage of completed documents"""
    total = Document.objects.filter(user=user).count()
    if total == 0:
        return 0

    completed = Document.objects.filter(user=user, status='completed').count()
    return int((completed / total) * 100)

def get_criteria_completion_status(user):
    """Get completion status for each eligibility criteria"""
    from django.db.models import Count

    # Get all criteria with document counts
    criteria_status = user.documents.filter(
        document_type='evidence'
    ).values(
        'related_criteria__id',
        'related_criteria__name',
        'related_criteria__criteria_type',
        'related_criteria__number_of_documents'
    ).annotate(
        document_count=Count('id'),
        completed_count=Count('id', filter=Q(status='completed'))
    ).order_by('related_criteria__criteria_type', 'related_criteria__name')

    return criteria_status