# expert_marketplace/urls.py
from django.urls import path
from . import views

app_name = 'expert_marketplace'

urlpatterns = [
    path('', views.book_consultation, name='expert_marketplace'),  # Changed from expert_list
    path('confirmation/', views.consultation_confirmation, name='consultation_confirmation'),
]