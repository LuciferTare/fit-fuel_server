from rest_framework import serializers

from notifications.models import NotificationTemplate


class NotificationTemplateSerializer(serializers.ModelSerializer):
    gym_name = serializers.CharField(source="gym.name", read_only=True, default=None)

    class Meta:
        model = NotificationTemplate
        fields = [
            "uuid",
            "gym",
            "gym_name",
            "title",
            "message",
            "category",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "gym", "gym_name", "created_at", "updated_at"]
