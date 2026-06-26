from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    ChangePasswordView,
    LoginView,
    RegisterView,
    ResendVerificationMailView,
    UserProfileView,
    VerifyEmailView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("verify-email/<uid>/<token>/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-verify-email/<uidb64>/", ResendVerificationMailView.as_view(), name="resend-verify-email"),
    path("token/", LoginView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("profile/", UserProfileView.as_view(), name="profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
]
