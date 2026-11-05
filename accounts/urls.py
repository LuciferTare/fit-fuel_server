from django.urls import path

from accounts.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    ProfileUpdateView,
    TokenRefreshAPIView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshAPIView.as_view(), name="auth-token-refresh"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("profile/", MeView.as_view(), name="auth-profile"),
    path("profile/update/", ProfileUpdateView.as_view(), name="auth-profile-update"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]
