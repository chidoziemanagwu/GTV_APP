from django.urls import path
from . import views
from .views import CustomLoginView, CustomSignupView

app_name = 'accounts'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('assessment/', views.assessment, name='assessment'),
    path('profile/', views.profile, name='profile'),
    path('visa-path-selection/', views.visa_path_selection, name='visa_path_selection'),
    path('profile/notifications/', views.update_notifications, name='update_notifications'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('digital-tech-path/', views.digital_tech_path, name='digital_tech_path'),
    path('document-checklist/', views.document_checklist, name='document_checklist'),
    path('expert-marketplace/', views.expert_marketplace, name='expert_marketplace'),
    path('final-submission/', views.final_submission, name='final_submission'),
    path('contact/', views.contact, name='contact'),
    path('login/', CustomLoginView.as_view(), name='account_login'),
    path('signup/', CustomSignupView.as_view(), name='account_signup'),
    path('terms-privacy/', views.terms_privacy, name='terms_privacy'),
]