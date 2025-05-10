# import os
# import django
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# from django.core.asgi import get_asgi_application

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tech_nation_visa_assistant.settings')
# django.setup()

# # Import websocket_urlpatterns after Django setup
# # We'll create this file later, so use a try/except to avoid errors during initial setup
# try:
#     from notion_monitor.routing import websocket_urlpatterns
# except ImportError:
#     websocket_urlpatterns = []

# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AuthMiddlewareStack(
#         URLRouter(
#             websocket_urlpatterns
#         )
#     ),
# })




# tech_nation_visa_assistant/asgi.py
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tech_nation_visa_assistant.settings')

application = get_asgi_application()