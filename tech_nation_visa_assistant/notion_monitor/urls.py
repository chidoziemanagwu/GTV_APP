from django.urls import path
from . import views

app_name = 'notion_monitor'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('changes/', views.change_list, name='change_list'),
    path('changes/<int:change_id>/', views.change_detail, name='change_detail'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/mark-read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('toggle-notifications/', views.toggle_notifications, name='toggle_notifications'),
    path('pages/add/', views.add_monitored_page, name='add_monitored_page'),
    path('pages/remove/<int:page_id>/', views.remove_monitored_page, name='remove_monitored_page'),
    path('manual-check/', views.manual_check, name='manual_check'),
]