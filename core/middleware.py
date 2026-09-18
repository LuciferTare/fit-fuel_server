from django.db.models import F
from django.utils import timezone

from core.models import DailyRequestCount

# The Django admin UI, served media/static files, and API docs aren't "API
# requests" in the sense the dashboard card means — everything else counts.
_EXCLUDED_PREFIXES = ("/admin/", "/media/", "/static/", "/schema/", "/docs/")


class RequestCounterMiddleware:
    """Tracks a simple per-day count of API requests, backing the admin
    dashboard's "API Requests Today" card. No cache backend is configured
    for this project (default per-process LocMemCache), so counting via a
    DB row updated with F() is what stays correct across multiple workers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(_EXCLUDED_PREFIXES):
            self._increment()
        return self.get_response(request)

    def _increment(self):
        today = timezone.localdate()
        updated = DailyRequestCount.objects.filter(date=today).update(
            count=F("count") + 1)
        if not updated:
            DailyRequestCount.objects.get_or_create(date=today, defaults={"count": 1})
