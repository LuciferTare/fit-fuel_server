from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import CustomUser, UserStatus, UserType
from accounts.serializers import (
    AssignTrainerSerializer,
    GymOwnerCreateSerializer,
    GymOwnerDetailSerializer,
    MemberCreateSerializer,
    MemberDetailSerializer,
    MemberProfileSerializer,
    TrainerCreateSerializer,
    TrainerDetailSerializer,
)
from core.exceptions import ConflictException
from core.pagination import CustomPagination
from core.permissions import IsAdmin, IsGymOwner, IsMember, IsTrainer
from core.views import BaseModelViewSet, BaseAPIView


# ── Admin: Gym Owner Management ───────────────────────────────────────────────

@extend_schema(tags=["Gym Owners"])
class GymOwnerViewSet(BaseModelViewSet):
    permission_classes = [IsAdmin]
    pagination_class = CustomPagination
    queryset = CustomUser.objects.none()  # overridden by get_queryset; needed for schema gen
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status"]
    search_fields = ["first_name", "last_name", "phone_number"]
    ordering_fields = ["first_name", "last_name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return CustomUser.active_objects.filter(user_type=UserType.GYM_OWNER)

    def get_serializer_class(self):
        if self.action == "create":
            return GymOwnerCreateSerializer
        return GymOwnerDetailSerializer

    def create(self, request, *args, **kwargs):
        phone = request.data.get("phone_number")
        if phone and CustomUser.objects.filter(phone_number=phone).exists():
            raise ConflictException("This phone number is already registered.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(
            user_type=UserType.GYM_OWNER,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Disable Gym Owner")
    @action(detail=True, methods=["patch"], url_path="disable")
    def disable(self, request, pk=None):
        owner = self.get_object()
        owner.status = UserStatus.DISABLED
        owner.updated_by = request.user
        owner.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(GymOwnerDetailSerializer(owner).data)


# ── Gym Owner: Trainer Management ─────────────────────────────────────────────

@extend_schema(tags=["Trainers"])
class TrainerViewSet(BaseModelViewSet):
    permission_classes = [IsGymOwner]
    pagination_class = CustomPagination
    queryset = CustomUser.objects.none()  # overridden by get_queryset; needed for schema gen
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status"]
    search_fields = ["first_name", "last_name", "phone_number"]
    ordering_fields = ["first_name", "last_name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return CustomUser.active_objects.filter(
            user_type=UserType.TRAINER,
            gym=self.request.user,
        )

    def get_serializer_class(self):
        if self.action == "create":
            return TrainerCreateSerializer
        return TrainerDetailSerializer

    def create(self, request, *args, **kwargs):
        phone = request.data.get("phone_number")
        if phone and CustomUser.objects.filter(phone_number=phone).exists():
            raise ConflictException("This phone number is already registered.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(
            user_type=UserType.TRAINER,
            gym=self.request.user,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Disable Trainer")
    @action(detail=True, methods=["patch"], url_path="disable")
    def disable(self, request, pk=None):
        trainer = self.get_object()
        trainer.status = UserStatus.DISABLED
        trainer.updated_by = request.user
        trainer.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(TrainerDetailSerializer(trainer).data)


# ── Gym Owner: Member Management ──────────────────────────────────────────────

@extend_schema(tags=["Members"])
class MemberViewSet(BaseModelViewSet):
    permission_classes = [IsGymOwner]
    pagination_class = CustomPagination
    queryset = CustomUser.objects.none()  # overridden by get_queryset; needed for schema gen
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "gender", "trainer"]
    search_fields = ["first_name", "last_name", "phone_number"]
    ordering_fields = ["first_name", "last_name", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return CustomUser.active_objects.filter(
            user_type=UserType.MEMBER,
            gym=self.request.user,
        )

    def get_serializer_class(self):
        if self.action == "create":
            return MemberCreateSerializer
        return MemberDetailSerializer

    def create(self, request, *args, **kwargs):
        phone = request.data.get("phone_number")
        if phone and CustomUser.objects.filter(phone_number=phone).exists():
            raise ConflictException("This phone number is already registered.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(
            user_type=UserType.MEMBER,
            gym=self.request.user,
            created_by=self.request.user,
        )

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Disable Member")
    @action(detail=True, methods=["patch"], url_path="disable")
    def disable(self, request, pk=None):
        member = self.get_object()
        member.status = UserStatus.DISABLED
        member.updated_by = request.user
        member.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(MemberDetailSerializer(member).data)

    @extend_schema(summary="Assign Trainer to Member")
    @action(detail=True, methods=["patch"], url_path="assign-trainer")
    def assign_trainer(self, request, pk=None):
        member = self.get_object()
        serializer = AssignTrainerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        trainer_uuid = serializer.validated_data["trainer_uuid"]
        try:
            trainer = CustomUser.active_objects.get(
                uuid=trainer_uuid,
                user_type=UserType.TRAINER,
                gym=request.user,
            )
        except CustomUser.DoesNotExist:
            return Response(
                {"detail": "Trainer not found in this gym."},
                status=status.HTTP_404_NOT_FOUND,
            )

        member.trainer = trainer
        member.updated_by = request.user
        member.save(update_fields=["trainer", "updated_by", "updated_at"])
        return Response(MemberDetailSerializer(member).data)


# ── Trainer: View Assigned Members ────────────────────────────────────────────

@extend_schema(tags=["Trainer Panel"])
class TrainerMemberViewSet(BaseModelViewSet):
    permission_classes = [IsTrainer]
    pagination_class = CustomPagination
    serializer_class = MemberDetailSerializer
    queryset = CustomUser.objects.none()  # overridden by get_queryset; needed for schema gen
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "phone_number"]
    ordering_fields = ["first_name", "last_name", "created_at"]
    ordering = ["-created_at"]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return CustomUser.active_objects.filter(
            user_type=UserType.MEMBER,
            trainer=self.request.user,
        )


# ── Member: Self Profile ──────────────────────────────────────────────────────

@extend_schema(tags=["Member Panel"])
class MemberProfileView(BaseAPIView):
    permission_classes = [IsMember]
    serializer_class = MemberProfileSerializer

    def get(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = self.get_serializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save(updated_by=request.user)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
