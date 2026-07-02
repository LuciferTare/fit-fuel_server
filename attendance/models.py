from django.conf import settings
from django.db import models

from core.models import BaseModel


class Attendance(BaseModel):
    """Tracks a single member gym visit (check-in / check-out with GPS)."""

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendances",
        limit_choices_to={"user_type": "member"},
    )
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    check_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_out_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "attendance"
        ordering = ["-check_in"]
        indexes = [
            models.Index(fields=["member", "check_in"], name="att_member_check_in_idx"),
        ]

    def __str__(self):
        return f"{self.member} — in:{self.check_in}"
