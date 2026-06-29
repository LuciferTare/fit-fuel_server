from django.urls import path

from accounts.user_views import MemberProfileView

urlpatterns = [
    path("profile/", MemberProfileView.as_view(), name="member-profile"),
]
