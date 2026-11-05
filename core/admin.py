from django.contrib import admin

from core.models import DailyRequestCount


@admin.register(DailyRequestCount)
class DailyRequestCountAdmin(admin.ModelAdmin):
    list_display = ["date", "count"]
    ordering = ["-date"]
    readonly_fields = ["date", "count"]

    def has_add_permission(self, request):
        return False
