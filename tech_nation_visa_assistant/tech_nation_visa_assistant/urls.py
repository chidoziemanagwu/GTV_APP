from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import home
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Password Reset URLs (place these before allauth.urls)
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='account/password_reset.html',
             email_template_name='emails/password_reset.html',
             subject_template_name='emails/password_reset_subject.txt',
             success_url='/password-reset/done/'
         ),
         name='password_reset'),

    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='account/password_reset_done.html'
         ),
         name='password_reset_done'),

    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='account/password_reset_confirm.html',
             success_url='/reset/done/'
         ),
         name='password_reset_confirm'),

    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='account/password_reset_complete.html'
         ),
         name='password_reset_complete'),

    # Other URLs
    path('accounts/', include('allauth.urls')),  # Django-allauth URLs
    path('accounts/', include('accounts.urls')),  # Your accounts URLs
    path('documents/', include('document_manager.urls', namespace='document_manager')),
    path('ai-assistant/', include('ai_assistant.urls', namespace='ai_assistant')),
    path('consultation/', include('expert_marketplace.urls', namespace='expert_marketplace')),
    path('monitor/', include('notion_monitor.urls', namespace='notion_monitor')),
    path('payments/', include('payments.urls')),
    path('referrals/', include('referrals.urls', namespace='referrals')),
    path('', home, name='home'),  # Keep home at root URL
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)