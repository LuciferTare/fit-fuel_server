from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from accounts.models import UserType
from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer, CheckInSerializer, CheckOutSerializer
from attendance.services import duplicate_checkin_error, geofence_error, photo_required_error
from core.pagination import OptionalPagination
from core.permissions import IsGymOwner, IsMember, IsTrainer
from core.views import BaseAPIView


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

        photo_error = photo_required_error(request.user, data.get("photo"))
        if photo_error:
            return Response({"detail": photo_error}, status=status.HTTP_400_BAD_REQUEST)

        dup_error = duplicate_checkin_error(request.user, data["timestamp"].date())
        if dup_error:
            return Response({"detail": dup_error}, status=status.HTTP_400_BAD_REQUEST)

        geo_error = geofence_error(request.user, data["lat"], data["lng"])
        if geo_error:
            return Response({"detail": geo_error}, status=status.HTTP_400_BAD_REQUEST)

        attendance = Attendance.objects.create(
            user=request.user,
            check_in=data["timestamp"],
            check_in_lat=data["lat"],
            check_in_lng=data["lng"],
            check_in_photo=data.get("photo") if is_trainer else None,
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(
            AttendanceSerializer(attendance, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


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

        photo_error = photo_required_error(request.user, data.get("photo"))
        if photo_error:
            return Response({"detail": photo_error}, status=status.HTTP_400_BAD_REQUEST)

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

        geo_error = geofence_error(request.user, data["lat"], data["lng"])
        if geo_error:
            return Response({"detail": geo_error}, status=status.HTTP_400_BAD_REQUEST)

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
        return Response(
            AttendanceSerializer(attendance, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


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
            return self.get_paginated_response(
                AttendanceSerializer(page, many=True, context={"request": request}).data
            )
        return Response(AttendanceSerializer(qs, many=True, context={"request": request}).data)
