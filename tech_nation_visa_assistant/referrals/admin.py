from django.contrib import admin, messages
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
    list_display = ('referred_user', 'referral_code', 'timestamp', 'has_been_rewarded', 'free_use_granted', 'points_awarded_at')
    list_filter = ('has_been_rewarded', 'free_use_granted', 'referral_code__user')
    search_fields = ('referred_user__email', 'referral_code__code')
    readonly_fields = ('timestamp', 'points_awarded_at')
    actions = ['award_rewards_action'] # Changed action name

    def award_rewards_action(self, request, queryset):
        """
        Admin action to manually trigger the reward process for selected referrals.
        Awards one free use to the referrer.
        """
        awarded_count = 0
        already_rewarded_count = 0
        error_count = 0

        for signup in queryset:
            if signup.has_been_rewarded:
                already_rewarded_count += 1
                continue # Skip if already rewarded

            # Ensure the referred user is a paying customer before awarding
            # This check might be important depending on your admin workflow
            if not signup.referred_user.profile.is_paid_user:
                messages.warning(request, f"Referral for {signup.referred_user.email} cannot be rewarded: User is not a paying customer.")
                error_count +=1
                continue

            if signup.award_rewards(): # Call the correct method
                awarded_count += 1
            else:
                error_count += 1
                messages.error(request, f"Failed to award rewards for referral: {signup.referred_user.email}. Check logs.")
        
        if awarded_count > 0:
            self.message_user(request, f"Successfully awarded rewards for {awarded_count} referral(s).", messages.SUCCESS)
        if already_rewarded_count > 0:
            self.message_user(request, f"{already_rewarded_count} referral(s) were already rewarded and were skipped.", messages.INFO)
        if error_count > 0:
            self.message_user(request, f"Could not process rewards for {error_count} referral(s).", messages.WARNING)

    award_rewards_action.short_description = "Award Free Use to Referrer (for selected signups)" # Updated description

@admin.register(ReferralClick)
class ReferralClickAdmin(admin.ModelAdmin):
    list_display = ('referral_code', 'ip_address', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('referral_code__code', 'ip_address')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'