from django.db.models import F
from django.utils import timezone

from core.models import DailyRequestCount

# The Django admin UI, served media/static files, API docs, and the liveness probe aren't "API requests" in the sense the dashboard card means — everything else counts.
_EXCLUDED_PREFIXES = ("/admin/", "/media/", "/static/", "/schema/", "/docs/", "/api/health/")
# Nor is a request that never actually reached a real, authorized endpoint: 401 = failed authentication ("pre-auth"), 404 = no matching route.
_EXCLUDED_STATUS_CODES = {401, 404}


class RequestCounterMiddleware:
    """Tracks a simple per-day count of API requests, backing the admin dashboard's "API Requests Today" card. Counts only once the response is known, so a request is counted at most once and only if it wasn't excluded by path or ended in a status that doesn't represent real API usage (see `_EXCLUDED_STATUS_CODES`). No cache backend is configured for this project (default per-process LocMemCache), so counting via a DB row updated with F() is what stays correct across multiple workers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            not request.path.startswith(_EXCLUDED_PREFIXES)
            and response.status_code not in _EXCLUDED_STATUS_CODES
        ):
            self._increment()
        return response

    def _increment(self):
        today = timezone.localdate()
        updated = DailyRequestCount.objects.filter(date=today).update(
            count=F("count") + 1)
        if not updated:
            DailyRequestCount.objects.get_or_create(date=today, defaults={"count": 1})
