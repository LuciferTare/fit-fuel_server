from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from accounts.models import CustomUser, Gym, Membership, MembershipStatus, Payment, UserStatus, UserType
from accounts.serializers import (
    AssignTrainerSerializer,
    GymOwnerCreateSerializer,
    GymOwnerDetailSerializer,
    GymSerializer,
    MemberCreateSerializer,
    MemberDetailSerializer,
    MemberPaymentResponseSerializer,
    MemberPaymentSerializer,
    MemberProfileSerializer,
    MembershipSerializer,
    PaymentSerializer,
    TrainerCreateSerializer,
    TrainerDetailSerializer,
    TrainerSummarySerializer,
)
from core.exceptions import ConflictException
from core.pagination import CustomPagination
from core.permissions import (
    IsAdmin,
    IsAdminOrGymOwner,
    IsAuthenticatedUser,
    IsGymOwner,
    IsMember,
    IsTrainer,
)
from core.views import BaseModelViewSet, BaseAPIView


# ── Gym Master Management ─────────────────────────────────────────────────────

@extend_schema(tags=["Gyms"])
class GymViewSet(BaseModelViewSet):
    queryset = Gym.active_objects.all()
    serializer_class = GymSerializer
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        if self.action == "enable":
            return Gym.objects.all()
        return Gym.active_objects.all()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticatedUser()]
        return [IsAdmin()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Enable Gym")
    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, pk=None):
        gym = self.get_object()
        gym.is_deleted = False
        gym.deleted_at = None
        gym.updated_by = request.user
        gym.save(update_fields=["is_deleted", "deleted_at", "updated_by", "updated_at"])
        return Response(GymSerializer(gym).data)


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

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = dict(self.get_serializer(instance).data)
        trainers = CustomUser.active_objects.filter(
            user_type=UserType.TRAINER, gym=instance
        ).order_by("-created_at")
        data["trainers"] = TrainerSummarySerializer(trainers, many=True).data
        return Response(data)

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
    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request, pk=None):
        owner = self.get_object()
        owner.status = UserStatus.DISABLED
        owner.updated_by = request.user
        owner.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(GymOwnerDetailSerializer(owner).data)

    @extend_schema(summary="Enable Gym Owner")
    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, pk=None):
        owner = self.get_object()
        owner.status = UserStatus.ACTIVE
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

        gym_owner = request.user
        current_count = CustomUser.active_objects.filter(
            user_type=UserType.TRAINER,
            gym=gym_owner,
        ).count()
        if current_count >= gym_owner.trainer_limit:
            raise DRFValidationError(
                {"trainer_limit": f"Trainer limit of {gym_owner.trainer_limit} has been reached."}
            )

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
    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request, pk=None):
        trainer = self.get_object()
        trainer.status = UserStatus.DISABLED
        trainer.updated_by = request.user
        trainer.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(TrainerDetailSerializer(trainer).data)

    @extend_schema(summary="Enable Trainer")
    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, pk=None):
        trainer = self.get_object()
        trainer.status = UserStatus.ACTIVE
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
    @action(detail=True, methods=["post"], url_path="disable")
    def disable(self, request, pk=None):
        member = self.get_object()
        member.status = UserStatus.DISABLED
        member.updated_by = request.user
        member.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(MemberDetailSerializer(member).data)

    @extend_schema(summary="Enable Member")
    @action(detail=True, methods=["post"], url_path="enable")
    def enable(self, request, pk=None):
        member = self.get_object()
        member.status = UserStatus.ACTIVE
        member.updated_by = request.user
        member.save(update_fields=["status", "updated_by", "updated_at"])
        return Response(MemberDetailSerializer(member).data)

    @extend_schema(summary="Assign Trainer to Member")
    @action(detail=True, methods=["post"], url_path="assign-trainer")
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

    def post(self, request):
        serializer = self.get_serializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save(updated_by=request.user)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ── Gym Owner: Membership Management ─────────────────────────────────────────

@extend_schema(tags=["Memberships"])
class MembershipViewSet(BaseModelViewSet):
    permission_classes = [IsAdminOrGymOwner]
    pagination_class = CustomPagination
    serializer_class = MembershipSerializer
    queryset = Membership.objects.none()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "member", "payment_mode"]
    ordering_fields = ["start_date", "end_date", "created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == UserType.ADMIN:
            return Membership.active_objects.all()
        return Membership.active_objects.filter(member__gym=user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Gym Owner: Payment Management ────────────────────────────────────────────

@extend_schema(tags=["Payments"])
class PaymentViewSet(BaseModelViewSet):
    permission_classes = [IsAdminOrGymOwner]
    pagination_class = CustomPagination
    serializer_class = PaymentSerializer
    queryset = Payment.objects.none()
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["mode", "membership"]
    ordering_fields = ["paid_on", "created_at"]
    ordering = ["-paid_on"]

    def get_queryset(self):
        user = self.request.user
        if user.user_type == UserType.ADMIN:
            qs = Payment.active_objects.all()
        else:
            qs = Payment.active_objects.filter(membership__member__gym=user)
        member_uuid = self.request.query_params.get("member")
        if member_uuid:
            qs = qs.filter(membership__member__uuid=member_uuid)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete(deleted_by=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Phase-3: Member-centric payment entry point ───────────────────────────────

@extend_schema(tags=["Member Payments"])
class MemberPaymentView(BaseAPIView):
    """POST /api/payments/ — record a membership payment and update member's membership dates.
    GET  /api/payments/?member_id= — list membership records for a member.
    """

    permission_classes = [IsAdminOrGymOwner]

    @extend_schema(request=MemberPaymentSerializer, responses=MemberPaymentResponseSerializer)
    def post(self, request):
        serializer = MemberPaymentSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        member_id = data["member_id"]

        qs = CustomUser.active_objects.filter(uuid=member_id, user_type=UserType.MEMBER)
        if request.user.user_type == UserType.GYM_OWNER:
            qs = qs.filter(gym=request.user)
        try:
            member = qs.get()
        except CustomUser.DoesNotExist:
            return Response({"detail": "Member not found."}, status=status.HTTP_404_NOT_FOUND)

        mode_map = {"Cash": "cash", "Online": "online"}
        membership = Membership.objects.create(
            member=member,
            start_date=data["start_date"],
            end_date=data["end_date"],
            amount_paid=data["amount"],
            payment_mode=mode_map[data["mode"]],
            plan=data.get("plan", ""),
            status=MembershipStatus.ACTIVE,
            created_by=request.user,
            updated_by=request.user,
        )

        member.membership_start = data["start_date"]
        member.membership_end = data["end_date"]
        member.membership_status = MembershipStatus.ACTIVE
        member.membership_plan = data.get("plan", "")
        member.updated_by = request.user
        member.save(
            update_fields=[
                "membership_start", "membership_end",
                "membership_status", "membership_plan",
                "updated_by", "updated_at",
            ]
        )

        return Response(
            MemberPaymentResponseSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=MembershipSerializer)
    def get(self, request):
        """List memberships filtered by member_id query param."""
        if request.user.user_type == UserType.ADMIN:
            qs = Membership.active_objects.all()
        else:
            qs = Membership.active_objects.filter(member__gym=request.user)

        member_id = request.query_params.get("member_id")
        if member_id:
            qs = qs.filter(member__uuid=member_id)

        return Response(MembershipSerializer(qs, many=True).data)
