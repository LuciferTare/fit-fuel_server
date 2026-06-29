from rest_framework.routers import DefaultRouter

from accounts.user_views import GymOwnerViewSet, MemberViewSet, TrainerViewSet

router = DefaultRouter()
router.register("gym-owners", GymOwnerViewSet, basename="gym-owner")
router.register("trainers", TrainerViewSet, basename="trainer")
router.register("members", MemberViewSet, basename="member")

urlpatterns = router.urls
