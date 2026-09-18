from django.urls import path

from core.views import UploadFileView, health_check, my_ip

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("my-ip/", my_ip, name="my-ip"),
    path("upload-file/", UploadFileView.as_view(), name="upload-file"),
]
