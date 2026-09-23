from django.contrib import admin

from notifications.models import NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "gym", "created_by", "created_at"]
    list_filter = ["category", "is_deleted"]
    search_fields = ["title", "message"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at", "created_by", "updated_by", "deleted_at"]
