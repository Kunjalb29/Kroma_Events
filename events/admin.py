from django.contrib import admin
from events.models import Event, Enrollment


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'language', 'location', 'starts_at', 'capacity', 'created_by']
    list_filter = ['language', 'location']
    search_fields = ['title', 'description', 'created_by__email']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'starts_at'


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['seeker', 'event', 'status', 'created_at', 'updated_at']
    list_filter = ['status']
    search_fields = ['seeker__email', 'event__title']
    readonly_fields = ['created_at', 'updated_at']
