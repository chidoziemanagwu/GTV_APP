from django.urls import path
from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('', views.chat_view, name='chat'),
    path('send-message/', views.send_message, name='send_message'),
    path('conversation/<int:conversation_id>/', views.conversation_view, name='conversation'),
    path('history/', views.query_history, name='history'),
    path('submit-feedback/', views.submit_feedback, name='submit_feedback'),  # Changed from feedback to submit-feedback

    # Document generation endpoints
    path('generate/personal-statement/', views.generate_personal_statement, name='generate_personal_statement'),
    path('generate/cv/', views.enhance_cv, name='enhance_cv'),
    path('generate/recommendation/', views.generate_recommendation_letter, name='generate_recommendation'),

    # Conversation management endpoints
    path('conversation/create/', views.create_conversation, name='create_conversation'),
    path('stream-message/', views.stream_message, name='stream_message'),
    path('conversation/<int:conversation_id>/rename/', views.rename_conversation, name='rename_conversation'),
    path('conversation/<int:conversation_id>/delete/', views.delete_conversation, name='delete_conversation'),
]