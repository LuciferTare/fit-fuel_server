from django.urls import path

from rest_framework.routers import DefaultRouter

from accounts.user_views import TrainerMemberViewSet

router = DefaultRouter()
router.register("members", TrainerMemberViewSet, basename="trainer-member")

urlpatterns = router.urls
