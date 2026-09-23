from django.db import models

from core.models import BaseModel


class NotificationCategory(models.TextChoices):
    GENERAL = "general", "General"
    PROMOTION = "promotion", "Promotion"
    ALERT = "alert", "Alert"
    REMINDER = "reminder", "Reminder"


class NotificationTemplate(BaseModel):
    """A reusable WhatsApp/SMS message template.

    ``gym`` is null for admin-authored templates, which are shared across
    every gym; it's set to the owner's own gym for gym_owner-authored
    templates, which stay private to that gym.
    """

    gym = models.ForeignKey(
        "accounts.Gym",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="notification_templates",
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(
        max_length=20,
        choices=NotificationCategory.choices,
        default=NotificationCategory.GENERAL,
        db_index=True,
    )

    class Meta:
        db_table = "notification_templates"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.category})"
