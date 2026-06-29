from rest_framework import serializers

from attendance.models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    """Full attendance record — used for responses."""

    class Meta:
        model = Attendance
        fields = [
            "uuid", "member", "check_in", "check_out",
            "check_in_lat", "check_in_lng",
            "check_out_lat", "check_out_lng",
        ]
        read_only_fields = ["uuid"]


class CheckInSerializer(serializers.Serializer):
    """Input for POST /api/attendance/checkin/."""

    member_id = serializers.UUIDField()
    timestamp = serializers.DateTimeField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)


class CheckOutSerializer(serializers.Serializer):
    """Input for POST /api/attendance/checkout/."""

    attendance_id = serializers.UUIDField()
    timestamp = serializers.DateTimeField()
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
