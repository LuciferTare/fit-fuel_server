"""
Backup / offline-sync endpoints.

POST /api/backup/upload/   — client pushes local changes (LWW conflict resolution)
GET  /api/backup/download/ — client pulls server changes since a timestamp
"""
import logging

from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer
from core.permissions import IsAdmin, IsGymOwner, IsTrainer
from core.views import BaseAPIView

logger = logging.getLogger(__name__)

# Map of model labels the client is allowed to sync.
# Extend this dict in Phase 4 when workout models are added.
_SYNCABLE = {
    "attendance.Attendance": Attendance,
}


class BackupUploadView(BaseAPIView):
    """POST /api/backup/upload/ — push client-side changes to the server.

    Payload:
        {
            "user_id": "<member uuid>",     // optional; informational
            "changes": [
                {"model": "attendance.Attendance", "action": "create|update|delete", "data": {...}},
                ...
            ]
        }

    Conflict resolution: Last-Write-Wins on updated_at timestamp.
    """

    permission_classes = [IsAdmin | IsGymOwner | IsTrainer]

    @extend_schema(tags=["Backup"])
    def post(self, request):
        changes = request.data.get("changes", [])
        if not isinstance(changes, list):
            return Response({"detail": "changes must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": []}

        for change in changes:
            model_label = change.get("model")
            action = change.get("action")
            data = change.get("data") or {}

            Model = _SYNCABLE.get(model_label)
            if Model is None:
                stats["errors"].append({"model": model_label, "error": "Unknown or unsupported model."})
                continue

            try:
                if action in ("create", "update"):
                    obj_uuid = data.get("uuid")
                    if obj_uuid:
                        try:
                            instance = Model.objects.get(uuid=obj_uuid)
                            # LWW: skip if server record is newer
                            client_ts_raw = data.get("updated_at")
                            if client_ts_raw:
                                client_ts = parse_datetime(str(client_ts_raw))
                                if client_ts and instance.updated_at and client_ts <= instance.updated_at:
                                    stats["skipped"] += 1
                                    continue
                            for field, value in data.items():
                                if field not in ("uuid", "created_at", "updated_at", "created_by", "updated_by"):
                                    setattr(instance, field, value)
                            instance.updated_by = request.user
                            instance.save()
                            stats["updated"] += 1
                        except Model.DoesNotExist:
                            safe_data = {
                                k: v for k, v in data.items()
                                if k not in ("created_at", "updated_at")
                            }
                            safe_data.setdefault("created_by", request.user)
                            safe_data["updated_by"] = request.user
                            Model.objects.create(**safe_data)
                            stats["created"] += 1
                    else:
                        safe_data = {
                            k: v for k, v in data.items()
                            if k not in ("created_at", "updated_at")
                        }
                        safe_data.setdefault("created_by", request.user)
                        safe_data["updated_by"] = request.user
                        Model.objects.create(**safe_data)
                        stats["created"] += 1

                elif action == "delete":
                    obj_uuid = data.get("uuid")
                    if obj_uuid:
                        try:
                            instance = Model.objects.get(uuid=obj_uuid)
                            instance.soft_delete(deleted_by=request.user)
                            stats["deleted"] += 1
                        except Model.DoesNotExist:
                            stats["skipped"] += 1
                else:
                    stats["errors"].append({"action": action, "error": "Unknown action."})

            except Exception as exc:
                logger.exception("Backup upload error — model=%s action=%s", model_label, action)
                stats["errors"].append({"model": model_label, "action": action, "error": str(exc)})

        return Response(stats, status=status.HTTP_200_OK)


class BackupDownloadView(BaseAPIView):
    """GET /api/backup/download/?user_id=<uuid>&since=<ISO timestamp>

    Returns server records changed since the given timestamp.
    """

    permission_classes = [IsAdmin | IsGymOwner | IsTrainer]

    @extend_schema(
        tags=["Backup"],
        parameters=[
            OpenApiParameter("user_id", str, description="Member UUID to filter by"),
            OpenApiParameter("since", str, description="ISO-8601 timestamp; returns records updated after this"),
        ],
    )
    def get(self, request):
        user_id = request.query_params.get("user_id")
        since_raw = request.query_params.get("since")

        qs = Attendance.active_objects.all()
        if user_id:
            qs = qs.filter(member__uuid=user_id)
        if since_raw:
            since_dt = parse_datetime(since_raw)
            if since_dt:
                qs = qs.filter(updated_at__gte=since_dt)

        return Response(
            {"changes": {"attendance": AttendanceSerializer(qs, many=True).data}},
            status=status.HTTP_200_OK,
        )
