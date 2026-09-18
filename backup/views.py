"""
Backup / offline-sync endpoints.

POST /api/backup/upload/   — client pushes local changes (LWW conflict resolution)
GET  /api/backup/download/ — client pulls server changes since a timestamp
"""
import logging

from django.db import transaction
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer
from backup.models import ExerciseSet, SessionExercise, SessionRestBreak, WorkoutSession
from core.pagination import OptionalPagination
from core.permissions import IsAdmin, IsAuthenticatedUser, IsGymOwner, IsTrainer
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
    pagination_class = OptionalPagination

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
            qs = qs.filter(user__uuid=user_id)
        if since_raw:
            since_dt = parse_datetime(since_raw)
            if since_dt:
                qs = qs.filter(updated_at__gte=since_dt)

        page = self.paginate_queryset(qs)
        if page is not None:
            attendance_payload = self.get_paginated_response(
                AttendanceSerializer(page, many=True).data
            ).data
        else:
            attendance_payload = AttendanceSerializer(qs, many=True).data

        return Response(
            {"changes": {"attendance": attendance_payload}},
            status=status.HTTP_200_OK,
        )


class WorkoutSyncUploadView(BaseAPIView):
    """POST /api/backup/workouts/upload/ — replace the authenticated user's
    entire server-side workout history with what's in the request body.

    Whole-history replace, not per-record merge: the local app never deletes
    old sessions (it only accumulates), so each sync's payload already IS
    the user's full history. Replacing avoids double-counting a session
    that was already synced in a previous call.

    Payload:
        {
            "sessions": [
                {
                    "session_date": "2026-01-15", "duration_minutes": 45,
                    "notes": "...", "calories_burned": 320.5, "is_rest_day": false,
                    "exercises": [
                        {
                            "exercise_name": "Barbell Squat", "body_part": "Legs",
                            "muscle": "Quads", "is_unilateral": false,
                            "set_type": "normal", "superset_group": null,
                            "sets": [
                                {"set_number": 1, "reps": 10, "weight_kg": 60.0,
                                 "duration_seconds": null, "speed_kmh": null}
                            ]
                        }
                    ],
                    "rest_breaks": [
                        {"duration_minutes": 2, "sort_index": 0}
                    ]
                }
            ]
        }
    """

    permission_classes = [IsAuthenticatedUser]

    @extend_schema(tags=["Backup"])
    def post(self, request):
        sessions_data = request.data.get("sessions", [])
        if not isinstance(sessions_data, list):
            return Response({"detail": "sessions must be a list."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                WorkoutSession.objects.filter(user=request.user).delete()
                for session_data in sessions_data:
                    session = WorkoutSession.objects.create(
                        user=request.user,
                        session_date=session_data.get("session_date"),
                        duration_minutes=session_data.get("duration_minutes") or 0,
                        notes=session_data.get("notes"),
                        calories_burned=session_data.get("calories_burned"),
                        is_rest_day=bool(session_data.get("is_rest_day", False)),
                        created_by=request.user,
                        updated_by=request.user,
                    )
                    for exercise_data in session_data.get("exercises", []):
                        exercise = SessionExercise.objects.create(
                            session=session,
                            exercise_name=exercise_data.get("exercise_name", ""),
                            body_part=exercise_data.get("body_part"),
                            muscle=exercise_data.get("muscle"),
                            is_unilateral=bool(exercise_data.get("is_unilateral", False)),
                            set_type=exercise_data.get("set_type") or "normal",
                            superset_group=exercise_data.get("superset_group"),
                            created_by=request.user,
                            updated_by=request.user,
                        )
                        for i, set_data in enumerate(exercise_data.get("sets", []), start=1):
                            ExerciseSet.objects.create(
                                exercise=exercise,
                                set_number=set_data.get("set_number") or i,
                                reps=set_data.get("reps"),
                                weight_kg=set_data.get("weight_kg"),
                                duration_seconds=set_data.get("duration_seconds"),
                                speed_kmh=set_data.get("speed_kmh"),
                                created_by=request.user,
                                updated_by=request.user,
                            )
                    for i, rest_data in enumerate(session_data.get("rest_breaks", [])):
                        SessionRestBreak.objects.create(
                            session=session,
                            duration_minutes=rest_data.get("duration_minutes") or 0,
                            sort_index=rest_data.get("sort_index", i),
                            created_by=request.user,
                            updated_by=request.user,
                        )
        except Exception as exc:
            logger.exception("Workout sync upload error")
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        synced_sessions = WorkoutSession.objects.filter(user=request.user).count()
        return Response({"synced_sessions": synced_sessions}, status=status.HTTP_200_OK)
