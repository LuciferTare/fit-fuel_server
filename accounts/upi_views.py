"""Direct-UPI manual-verification flow: payment settings, plans, payment requests.

Nothing here trusts the payer: a request only becomes a Membership + Payment when
the intended recipient calls `verify`. See DIRECT_UPI_MANUAL_VERIFICATION_PLAN.md.
"""
import datetime
import re

from django.core.files.storage import default_storage
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.models import (
    OPEN_REQUEST_STATUSES,
    CustomUser,
    Membership,
    MembershipPlan,
    MembershipStatus,
    Payment,
    PaymentMode,
    PaymentRequest,
    PaymentRequestStatus as S,
    PaymentStatus,
    UserStatus,
    UserType,
)
from accounts.utils import add_months
from core import renderers
from core.exceptions import ConflictException
from core.pagination import CustomPagination, OptionalPagination
from core.permissions import IsAdminOrGymOwner, IsGymOwner, IsMember
from core.views import BaseAPIView, BaseModelViewSet

REQUEST_WINDOW = datetime.timedelta(hours=24)
UPI_ID_RE = re.compile(r"^[A-Za-z0-9.\-_]{2,64}@[A-Za-z]{2,32}$")


# ── Serializers ────────────────────────────────────────────────────────────────

class PaymentSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["payment_upi_id", "payment_payee_name", "payment_qr"]

    def validate_payment_upi_id(self, value):
        value = value.strip()
        if value and not UPI_ID_RE.match(value):
            raise serializers.ValidationError("Enter a valid UPI ID, e.g. name@bank.")
        return value


class MembershipPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipPlan
        fields = ["uuid", "name", "amount", "duration_months", "is_active", "created_at"]
        read_only_fields = ["uuid", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate_duration_months(self, value):
        if not 1 <= value <= 60:
            raise serializers.ValidationError("Duration must be between 1 and 60 months.")
        return value


class PaymentRequestSerializer(serializers.ModelSerializer):
    payer_name = serializers.CharField(source="payer.get_full_name", read_only=True)
    payer_phone = serializers.CharField(source="payer.phone_number", read_only=True)
    qr_image = serializers.SerializerMethodField()

    class Meta:
        model = PaymentRequest
        fields = [
            "uuid", "invoice_number", "status", "payer", "payer_name", "payer_phone",
            "plan_name", "amount", "duration_months", "upi_id", "payee_name", "qr_image",
            "utr", "submitted_at", "expires_at", "decided_at", "rejection_reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_qr_image(self, obj):
        if not obj.qr_image:
            return None
        return self.context["request"].build_absolute_uri(default_storage.url(obj.qr_image))


class _CreateSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()


class _SubmitSerializer(serializers.Serializer):
    utr = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")


class _RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _expire_overdue():
    """Lazy expiry (plan §C): called at the top of every read/action — no scheduler."""
    PaymentRequest.objects.filter(
        status__in=OPEN_REQUEST_STATUSES, expires_at__lt=timezone.now()
    ).update(status=S.EXPIRED)


def _plans_for(user):
    """Active plans `user` may pay for: a member's gym owner's, or a gym owner's admin's."""
    plans = MembershipPlan.active_objects.filter(
        is_active=True, provider__is_deleted=False, provider__status=UserStatus.ACTIVE
    )
    if user.user_type == UserType.MEMBER:
        return plans.filter(provider=user.gym_id) if user.gym_id else plans.none()
    return plans.filter(provider__user_type=UserType.ADMIN)


# ── Views ──────────────────────────────────────────────────────────────────────

@extend_schema(tags=["UPI Payments"])
class PaymentSettingsMeView(BaseAPIView):
    """GET/POST /api/payment-settings/me/ — recipient's own UPI details (POST = partial update)."""

    permission_classes = [IsAdminOrGymOwner]
    serializer_class = PaymentSettingsSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        return Response(self.get_serializer(request.user).data)

    def post(self, request):
        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)


@extend_schema(tags=["UPI Payments"])
class MembershipPlanViewSet(BaseModelViewSet):
    permission_classes = [IsAdminOrGymOwner]
    serializer_class = MembershipPlanSerializer
    pagination_class = OptionalPagination
    queryset = MembershipPlan.objects.none()

    def get_queryset(self):
        return MembershipPlan.active_objects.filter(provider=self.request.user)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(provider=user, created_by=user, updated_by=user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete(deleted_by=self.request.user)

    @action(
        detail=False, methods=["get"],
        permission_classes=[IsMember | IsGymOwner], pagination_class=OptionalPagination,
    )
    def available(self, request):
        qs = _plans_for(request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(self.get_serializer(page, many=True).data)
        return Response(self.get_serializer(qs, many=True).data)


@extend_schema(tags=["UPI Payments"])
class PaymentRequestViewSet(viewsets.GenericViewSet):
    renderer_classes = (renderers.ResponseRenderer,)
    serializer_class = PaymentRequestSerializer
    pagination_class = CustomPagination
    queryset = PaymentRequest.objects.none()
    lookup_field = "uuid"

    def get_permissions(self):
        if self.action in ("incoming", "incoming_count", "verify", "reject"):
            return [IsAdminOrGymOwner()]
        return [(IsMember | IsGymOwner)()]

    def _respond(self, req, code=status.HTTP_200_OK):
        return Response(self.get_serializer(req).data, status=code)

    def _list(self, qs):
        qs = qs.select_related("payer")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def _locked(self, request, **filters):
        """Lock one request the caller is a party to (404 for anyone else)."""
        return get_object_or_404(
            PaymentRequest.objects.select_for_update().select_related("payer"),
            uuid=self.kwargs["uuid"], **filters,
        )

    # -- payer ---------------------------------------------------------------

    @extend_schema(request=_CreateSerializer, responses=PaymentRequestSerializer)
    def create(self, request):
        _expire_overdue()
        data = _CreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            # Row lock serialises concurrent creates by the same payer (duplicate guard).
            payer = CustomUser.objects.select_for_update().get(pk=request.user.pk)
            plan = get_object_or_404(
                _plans_for(payer).select_related("provider"), uuid=data.validated_data["plan_id"]
            )
            recipient = plan.provider
            if not recipient.payment_upi_id:
                return Response(
                    {"detail": "The recipient has not set up UPI payments yet."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            existing = PaymentRequest.objects.filter(
                payer=payer, plan=plan, status__in=OPEN_REQUEST_STATUSES
            ).first()
            if existing:
                return self._respond(existing)
            req = PaymentRequest.objects.create(
                payer=payer, recipient=recipient, plan=plan,
                plan_name=plan.name, amount=plan.amount, duration_months=plan.duration_months,
                upi_id=recipient.payment_upi_id,
                payee_name=recipient.payment_payee_name or recipient.get_full_name(),
                qr_image=recipient.payment_qr.name if recipient.payment_qr else "",
                expires_at=timezone.now() + REQUEST_WINDOW,
                created_by=payer, updated_by=payer,
            )
        return self._respond(req, status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        _expire_overdue()
        return self._list(PaymentRequest.objects.filter(payer=request.user, is_deleted=False))

    @extend_schema(request=_SubmitSerializer, responses=PaymentRequestSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        _expire_overdue()
        data = _SubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            req = self._locked(request, payer=request.user)
            if req.status != S.PENDING_PAYMENT:
                raise ConflictException(f"Request is already {req.status}.")
            req.status = S.SUBMITTED
            req.utr = data.validated_data["utr"].strip()
            req.submitted_at = timezone.now()
            req.expires_at = req.submitted_at + REQUEST_WINDOW
            req.updated_by = request.user
            req.save()
        return self._respond(req)

    @extend_schema(request=None, responses=PaymentRequestSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        _expire_overdue()
        with transaction.atomic():
            req = self._locked(request, payer=request.user)
            if req.status != S.PENDING_PAYMENT:
                raise ConflictException(f"Request is already {req.status}.")
            req.status = S.CANCELLED
            req.updated_by = request.user
            req.save()
        return self._respond(req)

    # -- recipient -----------------------------------------------------------

    @action(detail=False, methods=["get"])
    def incoming(self, request):
        _expire_overdue()
        qs = PaymentRequest.objects.filter(
            recipient=request.user, status=S.SUBMITTED, is_deleted=False
        ).order_by("submitted_at")
        return self._list(qs)

    @action(detail=False, methods=["get"], url_path="incoming-count")
    def incoming_count(self, request):
        _expire_overdue()
        count = PaymentRequest.objects.filter(
            recipient=request.user, status=S.SUBMITTED, is_deleted=False
        ).count()
        return Response({"count": count})

    @extend_schema(request=None, responses=PaymentRequestSerializer)
    @action(detail=True, methods=["post"])
    def verify(self, request, uuid=None):
        _expire_overdue()
        with transaction.atomic():
            req = self._locked(request, recipient=request.user)
            if req.status == S.VERIFIED:  # double-click / stale session: no second ledger row
                return self._respond(req)
            if req.status != S.SUBMITTED:
                raise ConflictException(f"Request is {req.status}; it cannot be verified.")

            payer = CustomUser.objects.select_for_update().get(pk=req.payer_id)
            now = timezone.now()
            today = timezone.localdate()
            # Dates are computed now, never at request creation.
            start = today
            if payer.membership_end and payer.membership_end >= today:
                start = payer.membership_end + datetime.timedelta(days=1)
            end = add_months(start, req.duration_months) - datetime.timedelta(days=1)

            membership = None
            if payer.user_type == UserType.MEMBER:  # gym-owner subscriptions have no Membership row
                membership = Membership.objects.create(
                    member=payer, start_date=start, end_date=end, plan=req.plan_name,
                    amount_paid=req.amount, payment_mode=PaymentMode.ONLINE,
                    status=MembershipStatus.ACTIVE,
                    created_by=request.user, updated_by=request.user,
                )
            payment = Payment.objects.create(
                paid_by=payer, membership=membership, amount=req.amount,
                mode=PaymentMode.ONLINE, status=PaymentStatus.PAID, paid_on=now,
                invoice_number=req.invoice_number,
                created_by=request.user, updated_by=request.user,
            )
            payer.membership_start = start
            payer.membership_end = end
            payer.membership_status = MembershipStatus.ACTIVE
            payer.membership_plan = req.plan_name
            payer.updated_by = request.user
            payer.save(update_fields=[
                "membership_start", "membership_end", "membership_status",
                "membership_plan", "updated_by", "updated_at",
            ])

            req.status = S.VERIFIED
            req.decided_at = now
            req.decided_by = request.user
            req.membership = membership
            req.payment = payment
            req.updated_by = request.user
            req.save()
        return self._respond(req)

    @extend_schema(request=_RejectSerializer, responses=PaymentRequestSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, uuid=None):
        _expire_overdue()
        data = _RejectSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        with transaction.atomic():
            req = self._locked(request, recipient=request.user)
            if req.status != S.SUBMITTED:
                raise ConflictException(f"Request is {req.status}; it cannot be rejected.")
            req.status = S.REJECTED
            req.rejection_reason = data.validated_data["reason"].strip()
            req.decided_at = timezone.now()
            req.decided_by = request.user
            req.updated_by = request.user
            req.save()
        return self._respond(req)
