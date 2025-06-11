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
    path('<int:pk>/set-as-chosen/', views.set_as_chosen, name='set_as_chosen'),
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

    # Document enhancement and AI features
    path('quick-generate/', views.quick_generate, name='quick_generate'),
    path('regenerate-section/', views.regenerate_section, name='regenerate_section'),
    path('<int:pk>/improve/', views.improve_document, name='improve_document'),
    path('<int:pk>/versions/', views.document_versions, name='document_versions'),
    path('compare/', views.compare_documents, name='compare_documents'),
    path('<int:pk>/feedback/', views.document_feedback, name='document_feedback'),
    path('<int:pk>/analytics/', views.document_analytics, name='document_analytics'),

    # Batch operations
    path('batch-process/', views.batch_process_documents, name='batch_process_documents'),

    # Requirements and templates
    path('requirements/<str:track>/', views.get_requirements, name='get_requirements'),

    # Dashboard and settings
    path('dashboard/', views.dashboard, name='dashboard'),

    # API and utilities
    path('api/usage-stats/', views.api_usage_stats, name='api_usage_stats'),
    path('api/clear-cache/', views.clear_cache, name='clear_cache'),
    path('health/', views.health_check, name='health_check'),
    path('recommendation-guide/', views.recommendation_guide, name='recommendation_guide'),



    path('purchase-points/', views.purchase_points, name='purchase_points'),
    path('checkout-package/<int:package_id>/', views.checkout_package, name='checkout_package'),
    path('process-payment/<int:package_id>/', views.process_payment, name='process_payment'),
    path('documents/check-points/', views.check_points, name='check_points'),
    path('check-pending-payments/', views.check_pending_payments, name='check_pending_payments'),

    path('payment-success/<str:transaction_id>/', views.payment_success, name='payment_success'),
    path('payment-failed/', views.payment_cancel, name='payment_failed'),

    path('payment-success-redirect/', views.payment_success_redirect, name='payment_success_redirect'),
]