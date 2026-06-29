from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import AuthenticationFailed, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.serializers import (
    AssignTrainerSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    UserMeSerializer,
)
from core.views import BaseAPIView, NoAuthAPIView


@extend_schema(summary="Login", tags=["Auth"])
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer

    from core import renderers
    renderer_classes = (renderers.ResponseRenderer,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed as exc:
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict):
                code = detail.get("code", "")
                if code.startswith("account_"):
                    return Response(
                        detail.get("detail", "Account access denied."),
                        status=status.HTTP_403_FORBIDDEN,
                    )
            return Response(
                "Invalid phone number or password.",
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {"detail": "Login successful", **serializer.validated_data},
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Refresh Token", tags=["Auth"])
class TokenRefreshAPIView(TokenRefreshView):
    from core import renderers
    renderer_classes = (renderers.ResponseRenderer,)


@extend_schema(summary="Logout", tags=["Auth"])
class LogoutView(BaseAPIView):
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        refresh_token = serializer.validated_data.get("refresh")
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                "Invalid or already blacklisted token.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response("Logged out successfully.")


@extend_schema(summary="Current User", tags=["Auth"])
class MeView(BaseAPIView):
    serializer_class = UserMeSerializer

    def get(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


@extend_schema(summary="Change Password", tags=["Auth"])
class ChangePasswordView(BaseAPIView):
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response("Password updated successfully.")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
