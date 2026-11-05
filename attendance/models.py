from django.conf import settings
from django.db import models

from accounts.models import UserType
from core.models import BaseModel


class Attendance(BaseModel):
    """Tracks a single self-logged gym visit (check-in / check-out with GPS)
    for a member or a trainer."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendances",
        limit_choices_to={"user_type__in": [UserType.MEMBER, UserType.TRAINER]},
    )
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    check_in_lat = models.DecimalField(max_digits=9, decimal_places=6)
    check_in_lng = models.DecimalField(max_digits=9, decimal_places=6)
    check_out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # Only ever populated for a TRAINER's check-in/out — members never send one.
    check_in_photo = models.ImageField(upload_to="attendance_photos/", null=True, blank=True)
    check_out_photo = models.ImageField(upload_to="attendance_photos/", null=True, blank=True)

    class Meta:
        db_table = "attendance"
        ordering = ["-check_in"]
        indexes = [
            models.Index(fields=["user", "check_in"], name="att_user_check_in_idx"),
        ]

    def __str__(self):
        return f"{self.user} — in:{self.check_in}"
