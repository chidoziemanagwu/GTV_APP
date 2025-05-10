# expert_marketplace/admin.py
from django.contrib import admin
from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'scheduled_date', 'scheduled_time', 'status', 'created_at')
    list_filter = ('status', 'scheduled_date')
    search_fields = ('name', 'email', 'description')
    ordering = ('-created_at',)

    fieldsets = (
        ('Client Information', {
            'fields': ('name', 'email', 'phone')
        }),
        ('Booking Details', {
            'fields': ('scheduled_date', 'scheduled_time', 'description', 'status')
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ('created_at', 'updated_at')