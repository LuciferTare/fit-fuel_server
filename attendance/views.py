from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from accounts.models import UserType
from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer, CheckInSerializer, CheckOutSerializer
from core.pagination import OptionalPagination
from core.permissions import IsGymOwner, IsMember, IsTrainer
from core.utils import haversine_distance_m
from core.views import BaseAPIView

# Check-in/out must be within this many meters of the user's gym.
ATTENDANCE_RADIUS_M = 50


def _user_gym_location(user):
    """(latitude, longitude) of the Gym `user`'s account belongs to, or
    None if the user isn't linked to a gym or that gym has no location set."""
    gym_owner = user.gym
    if gym_owner is None or gym_owner.gym_details is None:
        return None
    gym = gym_owner.gym_details
    if gym.latitude is None or gym.longitude is None:
        return None
    return gym.latitude, gym.longitude


def _geofence_error(user, lat, lng):
    """Response describing why `lat`/`lng` is rejected, or None if it's
    within ATTENDANCE_RADIUS_M of the user's gym."""
    location = _user_gym_location(user)
    if location is None:
        return Response(
            {"detail": "Your gym has no registered location. Contact your gym owner."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    distance = haversine_distance_m(lat, lng, *location)
    if distance > ATTENDANCE_RADIUS_M:
        return Response(
            {
                "detail": (
                    f"You are {distance:.0f}m away from your gym — check-in/out "
                    f"must be within {ATTENDANCE_RADIUS_M}m of the gym location."
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class CheckInView(BaseAPIView):
    """POST /api/attendance/checkin/ — self check-in for members and trainers.

    Members and trainers are guarded differently: a member's attendance is a
    single daily presence marker (no check-out concept at all — one check-in
    per calendar day is the whole record), while a trainer's is a shift-style
    open/close pairing that must be checked out before checking in again.
    """

    permission_classes = [IsMember | IsTrainer]

    @extend_schema(request=CheckInSerializer, responses=AttendanceSerializer, tags=["Attendance"])
    def post(self, request):
        serializer = CheckInSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        is_trainer = request.user.user_type == UserType.TRAINER

        if is_trainer and not data.get("photo"):
            return Response(
                {"detail": "A photo is required for check-in."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if is_trainer:
            already_checked_in = Attendance.active_objects.filter(
                user=request.user, check_out__isnull=True
            ).exists()
            duplicate_message = "You're already checked in."
        else:
            already_checked_in = Attendance.active_objects.filter(
                user=request.user, check_in__date=data["timestamp"].date()
            ).exists()
            duplicate_message = "You've already checked in today."
        if already_checked_in:
            return Response({"detail": duplicate_message}, status=status.HTTP_400_BAD_REQUEST)

        geofence_error = _geofence_error(request.user, data["lat"], data["lng"])
        if geofence_error:
            return geofence_error

        attendance = Attendance.objects.create(
            user=request.user,
            check_in=data["timestamp"],
            check_in_lat=data["lat"],
            check_in_lng=data["lng"],
            check_in_photo=data.get("photo") if is_trainer else None,
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


class CheckOutView(BaseAPIView):
    """POST /api/attendance/checkout/ — trainer-only self check-out, closing
    the requesting trainer's own open attendance record (no id needed in the
    request). Members have no check-out concept — their daily check-in is
    the whole attendance record."""

    permission_classes = [IsTrainer]

    @extend_schema(request=CheckOutSerializer, responses=AttendanceSerializer, tags=["Attendance"])
    def post(self, request):
        serializer = CheckOutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        if not data.get("photo"):
            return Response(
                {"detail": "A photo is required for trainer check-out."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendance = (
            Attendance.active_objects.filter(user=request.user, check_out__isnull=True)
            .order_by("-check_in")
            .first()
        )
        if attendance is None:
            return Response(
                {"detail": "No active check-in found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        geofence_error = _geofence_error(request.user, data["lat"], data["lng"])
        if geofence_error:
            return geofence_error

        attendance.check_out = data["timestamp"]
        attendance.check_out_lat = data["lat"]
        attendance.check_out_lng = data["lng"]
        attendance.check_out_photo = data["photo"]
        attendance.updated_by = request.user
        attendance.save(
            update_fields=[
                "check_out", "check_out_lat", "check_out_lng", "check_out_photo",
                "updated_by", "updated_at",
            ]
        )
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_200_OK)


class AttendanceListView(BaseAPIView):
    """GET /api/attendance/?date=&user_id= — list attendance records.

    Gym owners see every attendance record across their gym (members and
    trainers alike); trainers and members only ever see their own.
    """

    permission_classes = [IsGymOwner | IsTrainer | IsMember]
    pagination_class = OptionalPagination

    @extend_schema(tags=["Attendance"])
    def get(self, request):
        qs = Attendance.active_objects.select_related("user")

        if request.user.user_type == UserType.GYM_OWNER:
            qs = qs.filter(user__gym=request.user)
        else:
            qs = qs.filter(user=request.user)

        user_id = request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user__uuid=user_id)

        date = request.query_params.get("date")
        if date:
            qs = qs.filter(check_in__date=date)

        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(AttendanceSerializer(page, many=True).data)
        return Response(AttendanceSerializer(qs, many=True).data)
