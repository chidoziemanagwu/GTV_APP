# payments/urls.py
from django.urls import path
from . import views

app_name = 'payments'  # Make sure this line is present

urlpatterns = [
    path('process/<int:booking_id>/', views.process_payment, name='process_payment'),
    path('success/<int:booking_id>/', views.payment_success, name='payment_success'),
    path('cancel/<int:booking_id>/', views.payment_cancel, name='payment_cancel'),
    path('webhook/', views.webhook, name='webhook'),
]