from django.conf import settings
from django.db import models

from core.models import BaseModel


class WorkoutSession(BaseModel):
    """Server-side mirror of the local app's `workout_sessions` table.

    Sync is whole-history replace, not per-record merge: the local app never
    deletes old sessions (it only accumulates), so each sync payload already
    contains everything the user has ever logged. Replacing this user's rows
    entirely on every sync avoids double-counting instead of needing
    per-session dedup logic. See `backup.views.WorkoutSyncUploadView`.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_sessions"
    )
    session_date = models.DateField()
    duration_minutes = models.PositiveIntegerField(default=0)
    notes = models.TextField(null=True, blank=True)
    calories_burned = models.FloatField(null=True, blank=True)
    is_rest_day = models.BooleanField(default=False)

    class Meta:
        db_table = "backup_workout_sessions"
        indexes = [
            models.Index(fields=["user", "session_date"], name="wsession_user_date_idx"),
        ]

    def __str__(self):
        return f"{self.user} — {self.session_date}"


class SessionExercise(BaseModel):
    """Mirrors the local `session_exercises` table."""

    session = models.ForeignKey(WorkoutSession, on_delete=models.CASCADE, related_name="exercises")
    exercise_name = models.CharField(max_length=255)
    body_part = models.CharField(max_length=100, null=True, blank=True)
    muscle = models.CharField(max_length=100, null=True, blank=True)
    is_unilateral = models.BooleanField(default=False)
    set_type = models.CharField(max_length=20, default="normal")
    superset_group = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "backup_session_exercises"

    def __str__(self):
        return self.exercise_name


class ExerciseSet(BaseModel):
    """Mirrors the local `exercise_sets` table."""

    exercise = models.ForeignKey(SessionExercise, on_delete=models.CASCADE, related_name="sets")
    set_number = models.PositiveIntegerField()
    reps = models.PositiveIntegerField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    speed_kmh = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "backup_exercise_sets"

    def __str__(self):
        return f"{self.exercise.exercise_name} — set {self.set_number}"


class SessionRestBreak(BaseModel):
    """Mirrors the local `session_rest_breaks` table."""

    session = models.ForeignKey(WorkoutSession, on_delete=models.CASCADE, related_name="rest_breaks")
    duration_minutes = models.PositiveIntegerField(default=0)
    sort_index = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "backup_session_rest_breaks"
