from django.contrib import admin

from attendance.models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["user", "check_in", "check_out", "is_deleted"]
    list_filter = ["is_deleted"]
    search_fields = ["user__first_name", "user__last_name", "user__phone_number"]
    raw_id_fields = ["user"]
