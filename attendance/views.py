from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from accounts.models import CustomUser, UserType
from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer, CheckInSerializer, CheckOutSerializer
from core.permissions import IsGymOwner, IsTrainer
from core.views import BaseAPIView


class CheckInView(BaseAPIView):
    """POST /api/attendance/checkin/ — record a member check-in."""

    permission_classes = [IsGymOwner | IsTrainer]

    @extend_schema(request=CheckInSerializer, responses=AttendanceSerializer, tags=["Attendance"])
    def post(self, request):
        serializer = CheckInSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        qs = CustomUser.active_objects.filter(uuid=data["member_id"], user_type=UserType.MEMBER)
        if request.user.user_type == UserType.GYM_OWNER:
            qs = qs.filter(gym=request.user)
        else:
            qs = qs.filter(trainer=request.user)

        try:
            member = qs.get()
        except CustomUser.DoesNotExist:
            return Response(
                {"detail": "Member not found or not accessible."},
                status=status.HTTP_404_NOT_FOUND,
            )

        attendance = Attendance.objects.create(
            member=member,
            check_in=data["timestamp"],
            check_in_lat=data.get("lat"),
            check_in_lng=data.get("lng"),
            created_by=request.user,
            updated_by=request.user,
        )
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


class CheckOutView(BaseAPIView):
    """POST /api/attendance/checkout/ — record a member check-out."""

    permission_classes = [IsGymOwner | IsTrainer]

    @extend_schema(request=CheckOutSerializer, responses=AttendanceSerializer, tags=["Attendance"])
    def post(self, request):
        serializer = CheckOutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            attendance = Attendance.objects.get(uuid=data["attendance_id"], is_deleted=False)
        except Attendance.DoesNotExist:
            return Response(
                {"detail": "Attendance record not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if attendance.check_out is not None:
            return Response(
                {"detail": "Member is already checked out."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendance.check_out = data["timestamp"]
        attendance.check_out_lat = data.get("lat")
        attendance.check_out_lng = data.get("lng")
        attendance.updated_by = request.user
        attendance.save(
            update_fields=["check_out", "check_out_lat", "check_out_lng", "updated_by", "updated_at"]
        )
        return Response(AttendanceSerializer(attendance).data, status=status.HTTP_200_OK)


class AttendanceListView(BaseAPIView):
    """GET /api/attendance/?member_id=&date= — list attendance records."""

    permission_classes = [IsGymOwner | IsTrainer]

    @extend_schema(tags=["Attendance"])
    def get(self, request):
        qs = Attendance.active_objects.select_related("member")

        if request.user.user_type == UserType.GYM_OWNER:
            qs = qs.filter(member__gym=request.user)
        else:
            qs = qs.filter(member__trainer=request.user)

        member_id = request.query_params.get("member_id")
        if member_id:
            qs = qs.filter(member__uuid=member_id)

        date = request.query_params.get("date")
        if date:
            qs = qs.filter(check_in__date=date)

        return Response(AttendanceSerializer(qs, many=True).data)
