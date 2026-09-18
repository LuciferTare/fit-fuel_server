from django.urls import path

from reports.views import (
    ApiRequestsTodayView,
    GymSubscriptionExpiryView,
    InactiveMembersView,
    MembershipExpiryView,
    RevenueSummaryView,
    StorageUsageView,
    TrainerWorkloadView,
    WorkoutBackupsCountView,
)

urlpatterns = [
    path("inactive-members/", InactiveMembersView.as_view(), name="report-inactive-members"),
    path("trainer-workload/", TrainerWorkloadView.as_view(), name="report-trainer-workload"),
    path("membership-expiry/", MembershipExpiryView.as_view(), name="report-membership-expiry"),
    path("gym-subscription-expiry/", GymSubscriptionExpiryView.as_view(), name="report-gym-subscription-expiry"),
    path("revenue-summary/", RevenueSummaryView.as_view(), name="report-revenue-summary"),
    path("storage-usage/", StorageUsageView.as_view(), name="report-storage-usage"),
    path("api-requests-today/", ApiRequestsTodayView.as_view(), name="report-api-requests-today"),
    path("workout-backups-count/", WorkoutBackupsCountView.as_view(), name="report-workout-backups-count"),
]
