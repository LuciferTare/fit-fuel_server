from django.urls import path

from accounts.user_views import MemberPaymentView

urlpatterns = [
    path("", MemberPaymentView.as_view(), name="member-payment"),
]
