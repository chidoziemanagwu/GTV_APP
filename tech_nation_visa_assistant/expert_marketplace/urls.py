# expert_marketplace/urls.py
from django.urls import path
from . import views

app_name = 'expert_marketplace'

urlpatterns = [
    path('book/', views.book_consultation, name='book_consultation'),
    path('payment/<int:booking_id>/', views.payment_page, name='payment'),
    path('confirmation/<int:booking_id>/', views.booking_confirmation, name='booking_confirmation'),
    path('booking/<int:booking_id>/', views.booking_detail, name='booking_detail'),
    path('booking/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'), # Client cancellation
    path('my-bookings/', views.my_bookings, name='my_bookings'), # Generic, redirects based on user type
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
    
    # Admin-triggered completion (if different logic or template is needed than generic mark_meeting_complete)
    # path('admin/booking/<int:booking_id>/complete/', views.mark_consultation_complete, name='admin_mark_consultation_complete'), # Example if you keep it separate

    path('create-payment-intent/<int:booking_id>/', views.create_payment_intent, name='create_payment_intent'),
    path('confirm-payment/<int:booking_id>/', views.confirm_payment, name='confirm_payment'),

    path('client-bookings/', views.client_bookings, name='client_bookings'), # Specific client bookings view
    path('booking/<int:booking_id>/reschedule/', views.reschedule_booking, name='reschedule_booking'),
    
    path('booking/<int:booking_id>/mark-complete/', views.mark_meeting_complete, name='mark_meeting_complete'), # Used by client & staff
    path('booking/<int:booking_id>/report-noshow/', views.report_expert_noshow, name='report_expert_noshow'), # Client reports expert
    path('booking/<int:booking_id>/report-client-noshow/', views.report_client_noshow, name='report_client_noshow'), # Expert reports client
    
    path('expert/dispute-response/<uuid:dispute_code>/', views.expert_dispute_response, name='dispute_response'),

    # MODIFIED URL for expert cancelling their own confirmed booking for reassignment
    path('expert/booking/<int:booking_id>/cancel-reassign/', views.expert_cancel_and_reassign_view, name='expert_cancel_and_reassign'),
    
    # Expert Specific URLs
    path('expert/login/', views.expert_login_view, name='expert_login'),
    path('expert/logout/', views.expert_logout_view, name='expert_logout'),
    path('expert/dashboard/', views.expert_dashboard_view, name='expert_dashboard'), 
    path('expert/consultations/upcoming/', views.expert_upcoming_consultations_view, name='expert_upcoming_consultations'),
    path('expert/consultations/past/', views.expert_past_consultations_view, name='expert_past_consultations'),
    path('expert/profile-settings/', views.expert_profile_settings_view, name='expert_profile_settings'),
    path('expert/earnings/', views.expert_earnings_view, name='expert_earnings'),
    path('expert/support/', views.expert_support_view, name='expert_support'),
    path('expert/stripe/connect/', views.expert_stripe_connect_onboard_view, name='expert_stripe_connect_onboard'),
    path('expert/stripe/return/', views.expert_stripe_connect_return_view, name='expert_stripe_connect_return'),
    path('expert/stripe/login/', views.expert_stripe_login_link_view, name='expert_stripe_login_link'),
    path('earnings/request-instant-payout/', views.request_instant_payout_view, name='request_instant_payout'),
    path('expert/availability/', views.expert_availability_list_view, name='expert_availability_list'),
]