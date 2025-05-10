from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserProfile, AIConversation
from django.utils.html import format_html

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fieldsets = (
        ('Personal Information', {
            'fields': ('current_country', 'target_uk_region')
        }),
        ('Assessment Details', {
            'fields': (
                'assessment_completed',
                'tech_specializations',
                # Remove these fields as they belong to User, not UserProfile
                # 'has_recognition',
                # 'has_innovation',
                # 'has_contribution'
            )
        }),
        ('Progress Tracking', {
            'fields': (
                'documents_completed',
                'document_status',
                'expert_review_completed',
                'application_submitted'
            )
        }),
        ('AI Usage', {
            'fields': ('ai_queries_used', 'ai_queries_limit')
        }),
    )
    readonly_fields = ('assessment_completed', 'documents_completed')

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = (
        'email',
        'username',
        'first_name',
        'last_name',
        'account_type',
        'visa_path',
        'years_experience',
        'get_assessment_status',
        'is_staff'
    )
    list_filter = (
        'account_type',
        'visa_path',
        'application_stage',
        'is_technical',
        'is_business',
        'profile__assessment_completed',
        'is_staff'
    )
    fieldsets = UserAdmin.fieldsets + (
        ('Visa Application', {
            'fields': (
                'account_type',
                'application_stage',
                'visa_path',
                'is_technical',
                'is_business',
                'years_experience'
            )
        }),
        ('Subscription', {
            'fields': ('subscription_active', 'subscription_end_date')
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2'),
        }),
    )
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email',)

    def get_assessment_status(self, obj):
        if hasattr(obj, 'profile') and obj.profile.assessment_completed:
            return format_html(
                '<span style="color: green;">✓ Completed</span><br>'
                'Technical: {}<br>'
                'Business: {}<br>'
                'Years: {}<br>'
                'Path: {}',
                '✓' if obj.is_technical else '✗',
                '✓' if obj.is_business else '✗',
                obj.years_experience,
                obj.get_visa_path_display()
            )
        return format_html('<span style="color: red;">✗ Not Completed</span>')
    get_assessment_status.short_description = 'Assessment Status'

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'get_email',
        'assessment_completed',
        'get_background_type',
        'get_years_experience',
        'get_visa_path',
        'get_has_recognition',  # Add these methods
        'get_has_innovation',
        'get_has_contribution'
    )
    list_filter = (
        'assessment_completed',
        'documents_completed',
        'expert_review_completed',
        'application_submitted'
    )
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('assessment_completed', 'documents_completed')

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'current_country', 'target_uk_region')
        }),
        ('Assessment Details', {
            'fields': (
                'assessment_completed',
                'tech_specializations',
                # 'has_recognition',
                # 'has_innovation',
                # 'has_contribution'
            )
        }),
        ('Progress Tracking', {
            'fields': (
                'documents_completed',
                'document_status',
                'expert_review_completed',
                'application_submitted'
            )
        }),
        ('AI Usage', {
            'fields': ('ai_queries_used', 'ai_queries_limit')
        }),
    )

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'

    def get_background_type(self, obj):
        if obj.user.is_technical:
            return 'Technical'
        elif obj.user.is_business:
            return 'Business'
        return 'Not specified'
    get_background_type.short_description = 'Background'

    def get_years_experience(self, obj):
        return f'{obj.user.years_experience} years'
    get_years_experience.short_description = 'Experience'

    def get_visa_path(self, obj):
        return obj.user.get_visa_path_display()
    get_visa_path.short_description = 'Visa Path'


    def get_has_recognition(self, obj):
        return obj.user.has_recognition
    get_has_recognition.short_description = 'Recognition'
    get_has_recognition.boolean = True

    def get_has_innovation(self, obj):
        return obj.user.has_innovation
    get_has_innovation.short_description = 'Innovation'
    get_has_innovation.boolean = True

    def get_has_contribution(self, obj):
        return obj.user.has_contribution
    get_has_contribution.short_description = 'Contribution'
    get_has_contribution.boolean = True

@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'created_at', 'feedback_helpful')
    list_filter = ('category', 'feedback_helpful', 'created_at')
    search_fields = ('user__email', 'query', 'response')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Conversation', {
            'fields': ('query', 'response')
        }),
        ('Feedback', {
            'fields': ('category', 'feedback_helpful', 'user_feedback')
        }),
        ('Metadata', {
            'fields': ('conversation_context', 'created_at', 'updated_at')
        }),
    )