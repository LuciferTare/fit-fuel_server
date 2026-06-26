from django.urls import path

from core.views import health_check, my_ip, ping

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("ping/", ping, name="ping"),
    path("my-ip/", my_ip, name="my-ip"),
]
