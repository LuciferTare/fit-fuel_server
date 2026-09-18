from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.response import Response

from accounts.models import CustomUser, Payment, PaymentStatus, UserType
from attendance.models import Attendance
from backup.models import WorkoutSession
from core.models import DailyRequestCount
from core.pagination import OptionalPagination
from core.permissions import IsAdmin, IsGymOwner, IsTrainer
from core.views import BaseAPIView


class InactiveMembersView(BaseAPIView):
    """GET /api/reports/inactive-members/?days=N

    Gym owners see every inactive member in their gym; trainers see only
    their own assigned members.
    """

    permission_classes = [IsGymOwner | IsTrainer]
    pagination_class = OptionalPagination

    @extend_schema(
        tags=["Reports"],
        parameters=[OpenApiParameter("days", int, description="Inactivity threshold in days (default 7)")],
    )
    def get(self, request):
        days = int(request.query_params.get("days", 7))
        cutoff = timezone.now() - timedelta(days=days)

        latest_checkin_subq = (
            Attendance.active_objects.filter(user=OuterRef("pk"))
            .order_by("-check_in")
            .values("check_in")[:1]
        )

        scope = (
            Q(trainer=request.user)
            if request.user.user_type == UserType.TRAINER
            else Q(gym=request.user)
        )
        members = (
            CustomUser.active_objects.filter(scope, user_type=UserType.MEMBER)
            .annotate(last_visit=Subquery(latest_checkin_subq))
        )

        result = []
        today = timezone.now().date()
        for m in members:
            last = m.last_visit
            if last is None or last <= cutoff:
                if last:
                    days_inactive = (today - last.date()).days
                    last_visit_str = last.date().isoformat()
                else:
                    days_inactive = days
                    last_visit_str = None
                result.append(
                    {
                        "member_id": str(m.uuid),
                        "name": m.get_full_name(),
                        "last_visit": last_visit_str,
                        "days_inactive": days_inactive,
                    }
                )

        page = self.paginate_queryset(result)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(result)


class TrainerWorkloadView(BaseAPIView):
    """GET /api/reports/trainer-workload/

    Returns each trainer in the gym with their active member count.
    """

    permission_classes = [IsGymOwner]
    pagination_class = OptionalPagination

    @extend_schema(tags=["Reports"])
    def get(self, request):
        trainers = (
            CustomUser.active_objects.filter(user_type=UserType.TRAINER, gym=request.user)
            .annotate(
                member_count=Count(
                    "trainer_members",
                    filter=Q(
                        trainer_members__is_deleted=False,
                        trainer_members__user_type=UserType.MEMBER,
                    ),
                )
            )
        )

        result = [
            {
                "trainer_id": str(t.uuid),
                "name": t.get_full_name(),
                "member_count": t.member_count,
            }
            for t in trainers
        ]
        page = self.paginate_queryset(result)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(result)


class MembershipExpiryView(BaseAPIView):
    """GET /api/reports/membership-expiry/?days=X

    Returns members whose membership expires within the next X days (or already expired within X days).
    """

    permission_classes = [IsGymOwner]
    pagination_class = OptionalPagination

    @extend_schema(
        tags=["Reports"],
        parameters=[OpenApiParameter("days", int, description="Look-ahead window in days (default 7)")],
    )
    def get(self, request):
        days = int(request.query_params.get("days", 7))
        today = timezone.now().date()
        deadline = today + timedelta(days=days)

        members = CustomUser.active_objects.filter(
            user_type=UserType.MEMBER,
            gym=request.user,
            membership_end__isnull=False,
            membership_end__lte=deadline,
        )

        result = [
            {
                "member_id": str(m.uuid),
                "name": m.get_full_name(),
                "expiry_date": m.membership_end.isoformat(),
                "days_left": (m.membership_end - today).days,
            }
            for m in members
        ]
        page = self.paginate_queryset(result)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(result)


class GymSubscriptionExpiryView(BaseAPIView):
    """GET /api/reports/gym-subscription-expiry/?days=X — admin-only.

    Gym OWNER accounts whose own platform subscription (`membership_end`)
    expires within the next X days (or already has). Distinct from
    membership-expiry, which is about MEMBER subscriptions within one gym.
    """

    permission_classes = [IsAdmin]
    pagination_class = OptionalPagination

    @extend_schema(
        tags=["Reports"],
        parameters=[OpenApiParameter("days", int, description="Look-ahead window in days (default 7)")],
    )
    def get(self, request):
        days = int(request.query_params.get("days", 7))
        today = timezone.now().date()
        deadline = today + timedelta(days=days)

        owners = CustomUser.active_objects.filter(
            user_type=UserType.GYM_OWNER,
            membership_end__isnull=False,
            membership_end__lte=deadline,
        ).select_related("gym_details")

        result = [
            {
                "gym_owner_id": str(o.uuid),
                "name": o.get_full_name(),
                "gym_name": o.gym_details.name if o.gym_details else None,
                "expiry_date": o.membership_end.isoformat(),
                "days_left": (o.membership_end - today).days,
            }
            for o in owners
        ]
        page = self.paginate_queryset(result)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(result)


class RevenueSummaryView(BaseAPIView):
    """GET /api/reports/revenue-summary/

    Admin sees platform-wide revenue (gym-owner payments); gym owner sees
    their own gym's revenue (member payments) — same scoping as
    GET /payments/. `total_revenue`, `monthly_growth_percent`, and
    `total_transactions` are for the current calendar month;
    `pending_amount` is the current outstanding total regardless of when
    it was incurred.
    """

    permission_classes = [IsAdmin | IsGymOwner]

    @extend_schema(tags=["Reports"])
    def get(self, request):
        user = request.user
        qs = Payment.active_objects.all()
        if user.user_type == UserType.ADMIN:
            qs = qs.filter(paid_by__user_type=UserType.GYM_OWNER)
        else:
            qs = qs.filter(paid_by__user_type=UserType.MEMBER, paid_by__gym=user)

        now = timezone.now()
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

        paid_qs = qs.filter(status=PaymentStatus.PAID)
        this_month_qs = paid_qs.filter(paid_on__gte=this_month_start)
        last_month_qs = paid_qs.filter(paid_on__gte=last_month_start, paid_on__lt=this_month_start)

        this_month_total = this_month_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        last_month_total = last_month_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")

        if last_month_total:
            growth_percent = float((this_month_total - last_month_total) / last_month_total * 100)
        else:
            growth_percent = 100.0 if this_month_total else 0.0

        pending_amount = qs.filter(status=PaymentStatus.PENDING).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")

        method_breakdown = (
            this_month_qs.values("mode").annotate(total=Sum("amount")).order_by("-total")
        )

        return Response(
            {
                "total_revenue": this_month_total,
                "monthly_growth_percent": round(growth_percent, 1),
                "total_transactions": this_month_qs.count(),
                "pending_amount": pending_amount,
                "method_breakdown": [
                    {"method": row["mode"], "amount": row["total"]} for row in method_breakdown
                ],
            }
        )


class StorageUsageView(BaseAPIView):
    """GET /api/reports/storage-usage/ — admin-only total size (bytes) of
    everything under MEDIA_ROOT (profile pictures, gym pictures, attendance
    photos, uploaded music files, etc.)."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Reports"])
    def get(self, request):
        total_bytes = 0
        media_root = Path(settings.MEDIA_ROOT)
        if media_root.exists():
            for path in media_root.rglob("*"):
                if path.is_file():
                    try:
                        total_bytes += path.stat().st_size
                    except OSError:
                        continue
        return Response({"total_bytes": total_bytes})


class WorkoutBackupsCountView(BaseAPIView):
    """GET /api/reports/workout-backups-count/ — admin-only count of
    distinct users who have synced their workout history to the server via
    `POST /api/backup/workouts/upload/` (backup.models.WorkoutSession)."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Reports"])
    def get(self, request):
        count = WorkoutSession.objects.values("user").distinct().count()
        return Response({"count": count})


class ApiRequestsTodayView(BaseAPIView):
    """GET /api/reports/api-requests-today/ — admin-only count of API
    requests received so far today, tracked by
    `core.middleware.RequestCounterMiddleware`."""

    permission_classes = [IsAdmin]

    @extend_schema(tags=["Reports"])
    def get(self, request):
        today = timezone.localdate()
        row = DailyRequestCount.objects.filter(date=today).first()
        return Response({"count": row.count if row else 0})
