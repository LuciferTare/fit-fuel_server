from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth endpoints: /auth/login/, /auth/logout/, /auth/me/, etc.
    path("auth/", include("accounts.urls")),

    # Gym master data: /gyms/
    path("gyms/", include("accounts.urls_gyms")),

    # Gym Owner user management: /users/trainers/, /users/members/
    path("users/", include("accounts.urls_users")),

    # Trainer panel: /trainer/members/
    path("trainer/", include("accounts.urls_trainer")),

    # Member panel: /member/profile/
    path("member/", include("accounts.urls_member")),

    # Membership & Payment endpoints: /memberships/, /payments/
    path("", include("accounts.urls_memberships")),

    # Utility + Phase-3 API endpoints
    path("api/", include([
        path("", include("core.urls")),
        path("attendance/", include("attendance.urls")),
        path("reports/", include("reports.urls")),
        path("backup/", include("backup.urls")),
        path("payments/", include("accounts.urls_member_payments")),
    ])),

    # API docs
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            template_name="swagger-ui.html", url_name="schema"
        ),
        name="swagger-ui",
    ),
]

if not settings.DEBUG:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
        re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
    ]
else:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
