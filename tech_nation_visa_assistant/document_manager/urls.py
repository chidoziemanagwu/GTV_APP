# document_manager/urls.py
from django.urls import path
from . import views

app_name = 'document_manager'

urlpatterns = [
    path('', views.document_list, name='document_list'),
    path('partial/', views.document_list_partial, name='document_list_partial'),
    path('<int:document_id>/', views.document_detail, name='document_detail'),
    path('create/<str:doc_type>/', views.create_document, name='create_document'),
    path('personal-statement/', views.personal_statement_builder, name='personal_statement_builder'),
    # Add these new endpoints under personal-statement
    path('personal-statement/generate/', views.generate_personal_statement, name='generate_personal_statement'),
    path('personal-statement/download/', views.download_personal_statement, name='download_personal_statement'),
    path('evidence/', views.evidence_documents, name='evidence_documents'),
    # document_manager/urls.py
    path('personal-statement/save/', views.save_personal_statement, name='save_personal_statement'),
    path('<int:document_id>/delete/', views.delete_document, name='delete_document'),
    # urls.py
    path('cv/analyze/', views.analyze_cv, name='analyze_cv'),
    path('recommendation/', views.recommendation_guide, name='recommendation_guide'),
    path('<int:document_id>/set-as-chosen/', views.set_document_as_chosen, name='set_document_as_chosen'),
]