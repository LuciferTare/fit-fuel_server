from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status
from rest_framework.response import Response

from accounts.models import UserType
from core.pagination import CustomPagination
from core.permissions import IsAdminOrGymOwner
from core.views import BaseModelViewSet
from notifications.models import NotificationTemplate
from notifications.serializers import NotificationTemplateSerializer


@extend_schema(tags=["Notifications"])
class NotificationTemplateViewSet(BaseModelViewSet):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = NotificationTemplateSerializer
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "message"]
    ordering_fields = ["created_at", "title"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = NotificationTemplate.active_objects.select_related("gym")
        user = self.request.user
        if user.user_type == UserType.GYM_OWNER:
            if self.action in ("update", "partial_update_via_post", "destroy"):
                # Writes: own gym's templates only — global (admin-authored,
                # gym=null) templates are visible but read-only to a gym
                # owner, so they're excluded from the queryset get_object()
                # resolves against here. Out-of-scope UUID -> 404, same as
                # GymViewSet's own-row write scoping.
                qs = qs.filter(gym_id=user.gym_details_id)
            else:
                # Reads: own gym's templates plus admin-authored global ones.
                qs = qs.filter(Q(gym_id=user.gym_details_id) | Q(gym__isnull=True))
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        gym = user.gym_details if user.user_type == UserType.GYM_OWNER else None
        serializer.save(gym=gym, created_by=user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
