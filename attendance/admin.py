from django.contrib import admin

from attendance.models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["member", "check_in", "check_out", "is_deleted"]
    list_filter = ["is_deleted"]
    search_fields = ["member__first_name", "member__last_name", "member__phone_number"]
    raw_id_fields = ["member"]
