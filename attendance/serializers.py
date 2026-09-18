from rest_framework import serializers

from attendance.models import Attendance
from core.serializers import UploadedFileURLField


class AttendanceSerializer(serializers.ModelSerializer):
    """Full attendance record — used for responses."""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_type = serializers.CharField(source="user.user_type", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "uuid", "user", "user_name", "user_type",
            "check_in", "check_out",
            "check_in_lat", "check_in_lng",
            "check_out_lat", "check_out_lng",
            "check_in_photo", "check_out_photo",
        ]
        read_only_fields = ["uuid"]


class CheckInSerializer(serializers.Serializer):
    """Input for POST /api/attendance/checkin/ — self check-in.

    `photo` is optional here; whether it's actually required depends on the
    requesting user's role (mandatory for a trainer, unused for a member) —
    enforced in the view, since that needs `request.user`.
    """

    timestamp = serializers.DateTimeField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    photo = UploadedFileURLField()


class CheckOutSerializer(serializers.Serializer):
    """Input for POST /api/attendance/checkout/ — self check-out. See
    `CheckInSerializer` re: `photo`."""

    timestamp = serializers.DateTimeField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)
    photo = UploadedFileURLField()
