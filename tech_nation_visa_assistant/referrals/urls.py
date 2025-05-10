from django.urls import path
from . import views

app_name = 'referrals'

urlpatterns = [
    # Share page
    path('share/', views.share_link, name='share'),

    # API endpoints
    path('track-share/', views.track_share, name='track_share'),

    # Join with referral
    path('join/<str:code>/', views.join_with_referral, name='join_with_referral'),

    # Stats and tracking
    path('stats/', views.referral_stats, name='stats'),
]