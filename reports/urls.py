from django.urls import path

from reports.views import InactiveMembersView, MembershipExpiryView, TrainerWorkloadView

urlpatterns = [
    path("inactive-members/", InactiveMembersView.as_view(), name="report-inactive-members"),
    path("trainer-workload/", TrainerWorkloadView.as_view(), name="report-trainer-workload"),
    path("membership-expiry/", MembershipExpiryView.as_view(), name="report-membership-expiry"),
]
