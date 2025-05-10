from django.urls import path
from . import consumers

# This will be empty initially but will be populated with WebSocket consumer paths
websocket_urlpatterns = [
    # path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
]