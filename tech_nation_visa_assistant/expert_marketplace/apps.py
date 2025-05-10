# expert_marketplace/apps.py
from django.apps import AppConfig

class ExpertMarketplaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'expert_marketplace'

    def ready(self):
        try:
            from . import schedulers
            schedulers.start()
        except Exception as e:
            print(f"Error starting scheduler: {str(e)}")