from django.urls import path

from core.views import health_check, my_ip

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("my-ip/", my_ip, name="my-ip"),
]
