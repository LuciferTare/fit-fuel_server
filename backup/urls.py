from django.urls import path

from backup.views import (
    BackupDownloadView,
    BackupUploadView,
    BodyMeasurementSyncDownloadView,
    BodyMeasurementSyncUploadView,
    WorkoutSyncDownloadView,
    WorkoutSyncUploadView,
)

urlpatterns = [
    path("upload/", BackupUploadView.as_view(), name="backup-upload"),
    path("download/", BackupDownloadView.as_view(), name="backup-download"),
    path("workouts/upload/", WorkoutSyncUploadView.as_view(), name="backup-workouts-upload"),
    path("workouts/download/", WorkoutSyncDownloadView.as_view(), name="backup-workouts-download"),
    path(
        "body-measurements/upload/",
        BodyMeasurementSyncUploadView.as_view(),
        name="backup-body-measurements-upload",
    ),
    path(
        "body-measurements/download/",
        BodyMeasurementSyncDownloadView.as_view(),
        name="backup-body-measurements-download",
    ),
]
