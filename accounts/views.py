import threading

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.contrib.sites.shortcuts import get_current_site
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from accounts.models import CustomUser
from accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserProfileSerializer,
)
from core import renderers
from core.utils import mail_letter_sender
from core.views import BaseAPIView, NoAuthAPIView


@extend_schema(summary="Register", tags=["Accounts"])
class RegisterView(NoAuthAPIView):
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            user.is_active = False
            user.save()

            site_domain = get_current_site(request).domain
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            activation_url = f"http://{site_domain}/api/verify-email/{uid}/{token}/"

            context = {
                "user": user,
                "name": f"{user.first_name} {user.last_name}".strip() or user.username,
                "domain": site_domain,
                "uid": uid,
                "token": token,
                "activation_url": activation_url,
                "app_name": settings.APP_NAME,
                "logo_url": settings.LOGO_URL,
                "support_email": settings.SUPPORT_EMAIL,
            }

            email_subject = f"Verify Your Email - {settings.APP_NAME} Account Activation"
            html_message = render_to_string("acc_active_email.html", context)

            email = EmailMultiAlternatives(email_subject, email_subject, to=[user.email])
            email.attach_alternative(html_message, "text/html")

            email_thread = threading.Thread(target=email.send)
            email_thread.start()

            return Response(
                {"message": "User registered. Check email to verify."},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(summary="Verify Email", tags=["Accounts"])
class VerifyEmailView(NoAuthAPIView):
    def get(self, request, uid, token):
        try:
            uid_decoded = force_str(urlsafe_base64_decode(uid))
            user = CustomUser.objects.get(pk=uid_decoded)
            if default_token_generator.check_token(user, token):
                user.is_active = True
                user.is_email_verified = True
                user.save()
                return render(
                    request,
                    "verify_result.html",
                    {
                        "verified": True,
                        "name": f"{user.first_name} {user.last_name}".strip() or user.username,
                        "logo_url": settings.LOGO_URL,
                        "app_name": settings.APP_NAME,
                        "support_email": settings.SUPPORT_EMAIL,
                    },
                )
            return render(
                request,
                "verify_result.html",
                {
                    "verified": False,
                    "logo_url": settings.LOGO_URL,
                    "app_name": settings.APP_NAME,
                    "support_email": settings.SUPPORT_EMAIL,
                },
            )
        except Exception:
            return render(
                request,
                "verify_result.html",
                {
                    "verified": False,
                    "logo_url": settings.LOGO_URL,
                    "app_name": settings.APP_NAME,
                    "support_email": settings.SUPPORT_EMAIL,
                },
            )


@extend_schema(summary="Resend Verification Email", tags=["Accounts"])
class ResendVerificationMailView(NoAuthAPIView):
    def get(self, request, uidb64):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            return Response("User not found.", status=status.HTTP_400_BAD_REQUEST)

        if user.is_email_verified:
            return Response(
                "Your email is already verified.",
                status=status.HTTP_200_OK,
            )

        site_domain = get_current_site(request).domain
        uid_encoded = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        activation_url = f"http://{site_domain}/api/verify-email/{uid_encoded}/{token}/"

        context = {
            "user": user,
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "domain": site_domain,
            "uid": uid_encoded,
            "token": token,
            "activation_url": activation_url,
            "app_name": settings.APP_NAME,
            "logo_url": settings.LOGO_URL,
            "support_email": settings.SUPPORT_EMAIL,
        }

        mail_subject = f"Verify Your Email - {settings.APP_NAME} Account Activation"
        email_thread = threading.Thread(
            target=mail_letter_sender,
            args=(mail_subject, user.email, "acc_active_email.html", context),
        )
        email_thread.start()

        return Response(
            "Please check your inbox to verify your email address.",
            status=status.HTTP_200_OK,
        )


@extend_schema(summary="Login", tags=["Accounts"])
class LoginView(TokenObtainPairView):
    renderer_classes = (renderers.ResponseRenderer,)
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            return Response(
                "Invalid username or password.",
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


@extend_schema(summary="Profile", tags=["Accounts"])
class UserProfileView(GenericAPIView):
    renderer_classes = (renderers.ResponseRenderer,)
    serializer_class = UserProfileSerializer

    def get(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(summary="Change Password", tags=["Accounts"])
class ChangePasswordView(BaseAPIView):
    serializer_class = ChangePasswordSerializer

    def put(self, request):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({"detail": "Password updated successfully."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
