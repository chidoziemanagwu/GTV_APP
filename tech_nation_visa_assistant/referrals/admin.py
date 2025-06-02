from django.contrib import admin
from .models import ReferralCode, ReferralSignup, ReferralClick

@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'user', 'clicks', 'successful_referrals', 'created_at')
    search_fields = ('code', 'user__email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    list_filter = ('created_at',)
    date_hierarchy = 'created_at'

@admin.register(ReferralSignup)
class ReferralSignupAdmin(admin.ModelAdmin):
    list_display = ('referred_user', 'referral_code', 'points_awarded', 'points_awarded_at', 'timestamp')
    list_filter = ('points_awarded', 'timestamp')
    search_fields = ('referred_user__email', 'referral_code__code')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'
    actions = ['award_points_action']

    def award_points_action(self, request, queryset):
        count = 0
        for signup in queryset:
            if signup.award_points():
                count += 1
        self.message_user(request, f"Successfully awarded points for {count} referrals.")
    award_points_action.short_description = "Award points for selected referrals"

@admin.register(ReferralClick)
class ReferralClickAdmin(admin.ModelAdmin):
    list_display = ('referral_code', 'ip_address', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('referral_code__code', 'ip_address')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'