from django.urls import path

from backup.views import BackupDownloadView, BackupUploadView

urlpatterns = [
    path("upload/", BackupUploadView.as_view(), name="backup-upload"),
    path("download/", BackupDownloadView.as_view(), name="backup-download"),
]
