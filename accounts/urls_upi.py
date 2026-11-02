from django.urls import path
from rest_framework.routers import SimpleRouter

from accounts.upi_views import MembershipPlanViewSet, PaymentRequestViewSet, PaymentSettingsMeView

router = SimpleRouter()
router.register("membership-plans", MembershipPlanViewSet, basename="membership-plan")
router.register("payment-requests", PaymentRequestViewSet, basename="payment-request")

urlpatterns = [
    path("payment-settings/me/", PaymentSettingsMeView.as_view(), name="payment-settings-me"),
    *router.urls,
]
