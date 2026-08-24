from django.contrib import admin
from users.models import UserProfile, EmailOTP


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'is_verified', 'created_at']
    list_filter = ['role', 'is_verified']
    search_fields = ['user__email', 'user__username']
    readonly_fields = ['created_at']


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ['user', 'is_active', 'attempts_count', 'expires_at', 'created_at']
    list_filter = ['is_active']
    search_fields = ['user__email']
    readonly_fields = ['otp_hash', 'created_at']
