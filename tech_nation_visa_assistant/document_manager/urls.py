# document_manager/urls.py
from django.urls import path
from . import views

app_name = 'document_manager'

urlpatterns = [
    # Main document views
    path('', views.document_list, name='document_list'),
    path('partial/', views.document_list_partial, name='document_list_partial'),
    path('<int:pk>/', views.document_detail, name='document_detail'),
    path('create/', views.create_document, name='create_document'),
    path('<int:pk>/edit/', views.edit_document, name='edit_document'),
    path('<int:pk>/delete/', views.delete_document, name='delete_document'),
    path('<int:pk>/duplicate/', views.duplicate_document, name='duplicate_document'),
    path('<int:pk>/download/', views.download_document, name='download_document'),
    path('export/', views.export_documents, name='export_documents'),

    # Personal statement views
    path('personal-statement/', views.personal_statement_builder, name='personal_statement_builder'),
    path('personal-statement/generate/', views.generate_personal_statement, name='generate_personal_statement'),
    path('personal-statement/form/', views.personal_statement_form, name='personal_statement_form'),
    path('personal-statement/<int:pk>/preview/', views.preview_personal_statement, name='preview_personal_statement'),
    path('personal-statement/<int:pk>/update/', views.update_personal_statement, name='update_personal_statement'),
    path('personal-statement/save/', views.save_generated_content, name='save_generated_content'),

    # CV related views
    path('cv/upload/', views.cv_upload_form, name='cv_upload_form'),
    path('cv/analyze/', views.analyze_cv, name='analyze_cv'),

    # Generation and status tracking
    path('generation/status/<str:task_id>/', views.check_generation_status, name='check_generation_status'),
    path('generation/history/', views.generation_history, name='generation_history'),

    # AJAX and partial views
    path('form/partial/', views.document_form_partial, name='document_form_partial'),
    path('stats/', views.document_stats, name='document_stats'),
    path('quick-actions/', views.quick_actions, name='quick_actions'),
    path('<int:pk>/toggle-status/', views.toggle_document_status, name='toggle_document_status'),
    path('search/', views.search_documents, name='search_documents'),
    path('<int:pk>/preview/', views.document_preview, name='document_preview'),
    path('<int:pk>/notes/', views.update_document_notes, name='update_document_notes'),

    # Batch operations
    path('batch-process/', views.batch_process_documents, name='batch_process_documents'),

    # Requirements and templates
    path('requirements/<str:track>/', views.get_requirements, name='get_requirements'),
    path('templates/', views.template_library, name='template_library'),

    # Dashboard and settings
    path('dashboard/', views.dashboard, name='dashboard'),
    path('settings/', views.user_settings, name='user_settings'),

    # API and utilities
    path('api/usage-stats/', views.api_usage_stats, name='api_usage_stats'),
    path('api/clear-cache/', views.clear_cache, name='clear_cache'),
    path('api/test-ai/', views.test_ai_connection, name='test_ai_connection'),
    path('health/', views.health_check, name='health_check'),
]