import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated",
        editable=False,
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()
    active_objects = SoftDeleteManager()

    class Meta:
        abstract = True

    def soft_delete(self, deleted_by=None):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        if deleted_by:
            self.updated_by = deleted_by
        self.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])


class DailyRequestCount(models.Model):
    """One row per calendar date, incremented per-request by RequestCounterMiddleware — backs the admin dashboard's "API Requests Today" card. Not a BaseModel: this is an internal counter, not a business record (no uuid/audit trail needed)."""

    date = models.DateField(unique=True, db_index=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "daily_request_counts"

    def __str__(self):
        return f"{self.date}: {self.count}"
