from django.urls import path

from attendance.views import AttendanceListView, CheckInView, CheckOutView

urlpatterns = [
    path("", AttendanceListView.as_view(), name="attendance-list"),
    path("checkin/", CheckInView.as_view(), name="attendance-checkin"),
    path("checkout/", CheckOutView.as_view(), name="attendance-checkout"),
]
