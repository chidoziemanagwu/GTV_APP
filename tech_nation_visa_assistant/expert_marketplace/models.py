from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

class ExpertCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Expert Categories"

class Expert(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    profile_image = models.ImageField(upload_to='experts/', blank=True, null=True)
    title = models.CharField(max_length=100)
    bio = models.TextField()
    categories = models.ManyToManyField(ExpertCategory, related_name='experts')
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2)
    years_experience = models.PositiveIntegerField(default=0)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
        default=5.0
    )
    available = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-featured', '-rating']

class ExpertAvailability(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='availability')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        verbose_name_plural = "Expert Availabilities"
        unique_together = ('expert', 'day_of_week', 'start_time')

    def __str__(self):
        return f"{self.expert.name} - {self.get_day_of_week_display()} ({self.start_time} - {self.end_time})"

class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    # Make expert nullable for existing records
    expert = models.ForeignKey(Expert, on_delete=models.CASCADE, related_name='bookings', null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='expert_bookings', null=True, blank=True)
    name = models.CharField(max_length=100, default='')
    email = models.EmailField(default='')
    phone = models.CharField(max_length=20, default='')
    description = models.TextField(default='')
    scheduled_date = models.DateField(null=True)
    scheduled_time = models.TimeField(null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Consultation with {self.expert.name if self.expert else 'Unknown'} for {self.name} on {self.scheduled_date}"