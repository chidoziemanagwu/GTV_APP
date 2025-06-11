from django.urls import path
from . import views

app_name = 'custom_admin'

urlpatterns = [
    # Authentication
    path('login/', views.admin_login, name='login'),
    path('logout/', views.admin_logout, name='logout'),

    # Dashboard
    path('', views.admin_dashboard, name='dashboard'),

    # User Management
    path('users/', views.user_management, name='user_management'),
    path('users/<int:user_id>/details/', views.user_details, name='user_details'),
    path('users/<int:user_id>/update-points/', views.update_user_points, name='update_user_points'),
    path('users/<int:user_id>/toggle-status/', views.toggle_user_status, name='toggle_user_status'),
    path('users/send-message/<int:user_id>/', views.send_user_message, name='send_user_message'),
    path('users/bulk-action/', views.bulk_user_action, name='bulk_user_action'),

    # Analytics
    path('analytics/', views.analytics, name='analytics'),

    # Admin Management
    path('admins/', views.admin_management, name='admin_management'),

    # Activity Logs
    path('activity-logs/', views.activity_logs, name='activity_logs'),


    # Expert Management
    path('experts/', views.expert_management, name='expert_management'),
    path('experts/add/', views.add_expert, name='add_expert'),
    path('experts/<int:expert_id>/update/', views.update_expert, name='update_expert'),
    path('experts/<int:expert_id>/toggle-status/', views.toggle_expert_status, name='toggle_expert_status'),
    path('experts/<int:expert_id>/details/', views.expert_details, name='expert_details'),
    path('experts/bulk-action/', views.bulk_expert_action, name='bulk_expert_action'),

    # Add these to your existing urlpatterns
    path('referrals/', views.referral_management_dashboard, name='referral_dashboard'),
    path('referrals/award-points/<int:signup_id>/', views.award_referral_points, name='award_referral_points'),

    # Add this to your custom_admin/urls.py
    path('experts/<int:expert_id>/update-availability/', views.update_expert_availability, name='update_expert_availability'),
    
    # Contact message management
    path('contacts/', views.contact_messages_dashboard, name='contact_messages_dashboard'),
    path('contacts/<int:message_id>/', views.contact_message_detail, name='contact_message_detail'),
    path('contacts/<int:message_id>/update-status/', views.update_message_status, name='update_message_status'),
    

    # Add these to your urlpatterns
    path('consultations/', views.consultation_management, name='consultation_management'),
    path('consultations/<int:booking_id>/details/', views.booking_details_api, name='booking_details_api'),
    path('consultations/<int:booking_id>/update-status/', views.update_booking_status, name='update_booking_status'),
    path('consultations/<int:booking_id>/assign-expert/', views.assign_expert, name='assign_expert'),
    path('consultations/<int:booking_id>/available-experts/', views.available_experts_api, name='available_experts_api'),


    path('consultations/booking/<int:booking_id>/dispute/', views.get_dispute_by_booking_api, name='get_dispute_by_booking_api'),
    
    # Add these to your custom_admin/urls.py
    # path('consultations/disputes/', views.dispute_management, name='dispute_management'),
    path('consultations/dispute/<int:dispute_id>/', views.dispute_details, name='dispute_details'),
    path('consultations/dispute/<int:dispute_id>/status/', views.update_dispute_status, name='update_dispute_status'),
    path('consultations/dispute/<int:dispute_id>/resolve/', views.resolve_dispute, name='resolve_dispute'),


    path('payouts/', views.payout_management_view, name='payout_management'),
    path('payouts/earning/<int:earning_id>/update-status/', views.update_earning_payout_status_api, name='update_earning_payout_status_api'),
    path('payouts/bonus/<int:bonus_id>/update-status/', views.update_bonus_payout_status_api, name='update_bonus_payout_status_api'),
    
    # New URLs for initiating payouts
    path('payouts/earning/<int:earning_id>/initiate-payout/', views.initiate_earning_payout_api, name='initiate_earning_payout_api'),
    path('payouts/bonus/<int:bonus_id>/initiate-payout/', views.initiate_bonus_payout_api, name='initiate_bonus_payout_api'),
    
]