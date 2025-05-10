from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class AIQuery(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_queries')
    query_text = models.TextField()
    response_text = models.TextField()
    source_citations = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'AI Queries'

    def __str__(self):
        return f"Query by {self.user.email}: {self.query_text[:50]}..."

class AIFeedback(models.Model):
    RATING_CHOICES = (
        (1, '1 - Not Helpful'),
        (2, '2 - Somewhat Helpful'),
        (3, '3 - Helpful'),
        (4, '4 - Very Helpful'),
        (5, '5 - Extremely Helpful'),
    )

    query = models.ForeignKey(AIQuery, on_delete=models.CASCADE, related_name='feedback')
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback on query {self.query.id}: {self.rating}/5"

class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-updated_at']



class Message(models.Model):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    )

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"

    class Meta:
        ordering = ['created_at']