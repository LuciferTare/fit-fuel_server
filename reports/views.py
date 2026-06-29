from datetime import timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.response import Response

from accounts.models import CustomUser, UserType
from attendance.models import Attendance
from core.permissions import IsGymOwner
from core.views import BaseAPIView


class InactiveMembersView(BaseAPIView):
    """GET /api/reports/inactive-members/?days=N

    Returns gym members whose last check-in is older than N days (or who never checked in).
    """

    permission_classes = [IsGymOwner]

    @extend_schema(
        tags=["Reports"],
        parameters=[OpenApiParameter("days", int, description="Inactivity threshold in days (default 7)")],
    )
    def get(self, request):
        days = int(request.query_params.get("days", 7))
        cutoff = timezone.now() - timedelta(days=days)

        latest_checkin_subq = (
            Attendance.active_objects.filter(member=OuterRef("pk"))
            .order_by("-check_in")
            .values("check_in")[:1]
        )

        members = (
            CustomUser.active_objects.filter(user_type=UserType.MEMBER, gym=request.user)
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

        return Response(result)


class TrainerWorkloadView(BaseAPIView):
    """GET /api/reports/trainer-workload/

    Returns each trainer in the gym with their active member count.
    """

    permission_classes = [IsGymOwner]

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
        return Response(result)


class MembershipExpiryView(BaseAPIView):
    """GET /api/reports/membership-expiry/?days=X

    Returns members whose membership expires within the next X days (or already expired within X days).
    """

    permission_classes = [IsGymOwner]

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
        return Response(result)
