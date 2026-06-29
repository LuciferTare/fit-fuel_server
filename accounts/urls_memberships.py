from rest_framework.routers import DefaultRouter

from accounts.user_views import MembershipViewSet, PaymentViewSet

router = DefaultRouter()
router.register("memberships", MembershipViewSet, basename="membership")
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = router.urls
