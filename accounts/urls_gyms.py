from rest_framework.routers import DefaultRouter

from accounts.user_views import GymViewSet

router = DefaultRouter()
router.register("", GymViewSet, basename="gym")

urlpatterns = router.urls
