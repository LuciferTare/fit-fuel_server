from django.contrib import admin

from backup.models import ExerciseSet, SessionExercise, SessionRestBreak, WorkoutSession


@admin.register(WorkoutSession)
class WorkoutSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "session_date", "duration_minutes", "is_rest_day"]
    list_filter = ["is_rest_day"]
    search_fields = ["user__first_name", "user__last_name", "user__phone_number"]
    raw_id_fields = ["user"]


@admin.register(SessionExercise)
class SessionExerciseAdmin(admin.ModelAdmin):
    list_display = ["exercise_name", "session", "body_part", "set_type"]
    search_fields = ["exercise_name"]
    raw_id_fields = ["session"]


@admin.register(ExerciseSet)
class ExerciseSetAdmin(admin.ModelAdmin):
    list_display = ["exercise", "set_number", "reps", "weight_kg"]
    raw_id_fields = ["exercise"]


@admin.register(SessionRestBreak)
class SessionRestBreakAdmin(admin.ModelAdmin):
    list_display = ["session", "duration_minutes", "sort_index"]
    raw_id_fields = ["session"]
