from rest_framework.routers import DefaultRouter

from notifications.views import NotificationTemplateViewSet

router = DefaultRouter()
router.register("templates", NotificationTemplateViewSet, basename="notification-template")

urlpatterns = router.urls
