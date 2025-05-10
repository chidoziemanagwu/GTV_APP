# expert_marketplace/models.py
from django.db import models

class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    name = models.CharField(max_length=100, default='')
    email = models.EmailField(default='')
    phone = models.CharField(max_length=20, default='')
    description = models.TextField(default='')  # Added default
    scheduled_date = models.DateField(null=True)  # Made nullable
    scheduled_time = models.TimeField(null=True)  # Made nullable
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Consultation booking for {self.name} on {self.scheduled_date}"