"""
Backup / offline-sync endpoints.

POST /api/backup/upload/   — client pushes local changes (LWW conflict resolution)
GET  /api/backup/download/ — client pulls server changes since a timestamp
"""
import logging

from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.response import Response

from accounts.models import CustomUser, UserType
from attendance.models import Attendance
from attendance.serializers import AttendanceSerializer
from attendance.services import duplicate_checkin_error, geofence_error, photo_required_error
from backup.models import BodyMeasurement, ExerciseSet, SessionExercise, SessionRestBreak, WorkoutSession
from core.pagination import OptionalPagination
from core.permissions import IsAdmin, IsAuthenticatedUser, IsGymOwner, IsTrainer
from core.views import BaseAPIView

logger = logging.getLogger(__name__)

# Map of model labels the client is allowed to sync.
# Extend this dict in Phase 4 when workout models are added.
_SYNCABLE = {
    "attendance.Attendance": Attendance,
}


def _attendance_scope_q(user):
    """Which Attendance rows `user` may read/write through backup sync.
    Mirrors AttendanceListView's own-gym rule for gym owners; trainers are
    additionally scoped to their assigned members (plus their own rows,
    since trainers have their own check-in/out history to back up too)."""
    if user.user_type == UserType.ADMIN:
        return Q()
    if user.user_type == UserType.GYM_OWNER:
        return Q(user__gym=user)
    if user.user_type == UserType.TRAINER:
        return Q(user=user) | Q(user__trainer=user)
    return Q(pk__isnull=True)


def _can_write_attendance_for(caller, target_user):
    """Whether `caller` may create/update/delete an Attendance row belonging
    to `target_user` via backup sync — same boundary as `_attendance_scope_q`,
    just evaluated against one specific user instead of as a queryset filter."""
    if target_user is None:
        return False
    if caller.user_type == UserType.ADMIN:
        return True
    if caller.user_type == UserType.GYM_OWNER:
        return target_user.gym_id == caller.uuid
    if caller.user_type == UserType.TRAINER:
        return target_user.uuid == caller.uuid or target_user.trainer_id == caller.uuid
    return False


def _attendance_rule_error(target_user, data, is_create):
    """Applies the same rules `attendance.views.CheckInView`/`CheckOutView`
    enforce live (attendance.services) to a backup-sync create/update, based
    on whichever of the check-in/check-out fields are present in `data`."""
    if any(k in data for k in ("check_in", "check_in_lat", "check_in_lng", "check_in_photo")):
        error = photo_required_error(target_user, data.get("check_in_photo"))
        if error:
            return error
        if is_create and data.get("check_in"):
            check_in_dt = parse_datetime(str(data["check_in"]))
            if check_in_dt:
                error = duplicate_checkin_error(target_user, check_in_dt.date())
                if error:
                    return error
        lat, lng = data.get("check_in_lat"), data.get("check_in_lng")
        if lat is not None and lng is not None:
            error = geofence_error(target_user, lat, lng)
            if error:
                return error

    if any(k in data for k in ("check_out", "check_out_lat", "check_out_lng", "check_out_photo")):
        error = photo_required_error(target_user, data.get("check_out_photo"))
        if error:
            return error
        lat, lng = data.get("check_out_lat"), data.get("check_out_lng")
        if lat is not None and lng is not None:
            error = geofence_error(target_user, lat, lng)
            if error:
                return error

    return None


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
                    instance = Model.objects.filter(uuid=obj_uuid).first() if obj_uuid else None

                    if Model is Attendance:
                        target_user = (
                            instance.user if instance is not None
                            else CustomUser.objects.filter(uuid=data.get("user_id")).first()
                        )
                        if not _can_write_attendance_for(request.user, target_user):
                            stats["errors"].append({
                                "model": model_label, "action": action,
                                "error": "Not authorized to write attendance for this user.",
                            })
                            continue
                        rule_error = _attendance_rule_error(target_user, data, is_create=instance is None)
                        if rule_error:
                            stats["errors"].append({"model": model_label, "action": action, "error": rule_error})
                            continue

                    if instance is not None:
                        # LWW: skip if server record is newer
                        client_ts_raw = data.get("updated_at")
                        if client_ts_raw:
                            client_ts = parse_datetime(str(client_ts_raw))
                            if client_ts and instance.updated_at and client_ts <= instance.updated_at:
                                stats["skipped"] += 1
                                continue
                        excluded_fields = {"uuid", "created_at", "updated_at", "created_by", "updated_by"}
                        if Model is Attendance:
                            # Ownership is immutable once created — otherwise the
                            # scope check above (run against the *current* owner)
                            # could be bypassed by reassigning the row afterwards.
                            excluded_fields.add("user_id")
                        for field, value in data.items():
                            if field not in excluded_fields:
                                setattr(instance, field, value)
                        instance.updated_by = request.user
                        instance.save()
                        stats["updated"] += 1
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
                    instance = Model.objects.filter(uuid=obj_uuid).first() if obj_uuid else None
                    if instance is None:
                        stats["skipped"] += 1
                    elif Model is Attendance and not _can_write_attendance_for(request.user, instance.user):
                        stats["errors"].append({
                            "model": model_label, "action": action,
                            "error": "Not authorized to delete attendance for this user.",
                        })
                    else:
                        instance.soft_delete(deleted_by=request.user)
                        stats["deleted"] += 1
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

        qs = Attendance.active_objects.filter(_attendance_scope_q(request.user))
        if user_id:
            qs = qs.filter(user__uuid=user_id)
        if since_raw:
            since_dt = parse_datetime(since_raw)
            if since_dt:
                qs = qs.filter(updated_at__gte=since_dt)

        page = self.paginate_queryset(qs)
        if page is not None:
            attendance_payload = self.get_paginated_response(
                AttendanceSerializer(page, many=True, context={"request": request}).data
            ).data
        else:
            attendance_payload = AttendanceSerializer(
                qs, many=True, context={"request": request}
            ).data

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

    An empty or missing `sessions` array is rejected with 422 and makes no
    changes — it never wipes existing history, since that would otherwise
    look identical to "user genuinely has nothing to sync".

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
        if not sessions_data:
            return Response(
                {"detail": "sessions was empty or missing; no changes were made to avoid erasing existing history."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

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


class WorkoutSyncDownloadView(BaseAPIView):
    """GET /api/backup/workouts/download/ — return the authenticated user's
    entire server-side workout history, nested in the same shape
    `WorkoutSyncUploadView` accepts.
    """

    permission_classes = [IsAuthenticatedUser]

    @extend_schema(tags=["Backup"])
    def get(self, request):
        sessions = (
            WorkoutSession.objects.filter(user=request.user)
            .prefetch_related("exercises__sets", "rest_breaks")
            .order_by("session_date")
        )

        sessions_payload = []
        for session in sessions:
            sessions_payload.append(
                {
                    "session_date": session.session_date.isoformat(),
                    "duration_minutes": session.duration_minutes,
                    "notes": session.notes,
                    "calories_burned": session.calories_burned,
                    "is_rest_day": session.is_rest_day,
                    "exercises": [
                        {
                            "exercise_name": exercise.exercise_name,
                            "body_part": exercise.body_part,
                            "muscle": exercise.muscle,
                            "is_unilateral": exercise.is_unilateral,
                            "set_type": exercise.set_type,
                            "superset_group": exercise.superset_group,
                            "sets": [
                                {
                                    "set_number": s.set_number,
                                    "reps": s.reps,
                                    "weight_kg": s.weight_kg,
                                    "duration_seconds": s.duration_seconds,
                                    "speed_kmh": s.speed_kmh,
                                }
                                for s in exercise.sets.all()
                            ],
                        }
                        for exercise in session.exercises.all()
                    ],
                    "rest_breaks": [
                        {
                            "duration_minutes": rb.duration_minutes,
                            "sort_index": rb.sort_index,
                        }
                        for rb in session.rest_breaks.all()
                    ],
                }
            )

        return Response({"sessions": sessions_payload}, status=status.HTTP_200_OK)


class BodyMeasurementSyncUploadView(BaseAPIView):
    """POST /api/backup/body-measurements/upload/ — replace the authenticated
    user's entire server-side body-measurement history with what's in the
    request body.

    Whole-history replace, same rationale as WorkoutSyncUploadView. An empty
    or missing `measurements` array is rejected with 422 and makes no
    changes, for the same reason.

    Payload:
        {
            "measurements": [
                {
                    "age": 28, "gender": "male", "is_correction": false,
                    "weight_kg": 72.5, "height_cm": 178.0, "chest_cm": 100.0,
                    "waist_cm": 82.0, "biceps_cm": 35.0, "thighs_cm": 55.0,
                    "neck_cm": 38.0, "hip_cm": 95.0, "body_fat_percent": 15.5,
                    "recorded_at": "2026-01-15T08:30:00Z"
                }
            ]
        }
    """

    permission_classes = [IsAuthenticatedUser]

    @extend_schema(tags=["Backup"])
    def post(self, request):
        measurements_data = request.data.get("measurements", [])
        if not isinstance(measurements_data, list):
            return Response({"detail": "measurements must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        if not measurements_data:
            return Response(
                {"detail": "measurements was empty or missing; no changes were made to avoid erasing existing history."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        try:
            with transaction.atomic():
                BodyMeasurement.objects.filter(user=request.user).delete()
                for m in measurements_data:
                    BodyMeasurement.objects.create(
                        user=request.user,
                        age=m.get("age"),
                        gender=m.get("gender"),
                        is_correction=bool(m.get("is_correction", False)),
                        weight_kg=m.get("weight_kg"),
                        height_cm=m.get("height_cm"),
                        chest_cm=m.get("chest_cm"),
                        waist_cm=m.get("waist_cm"),
                        biceps_cm=m.get("biceps_cm"),
                        thighs_cm=m.get("thighs_cm"),
                        neck_cm=m.get("neck_cm"),
                        hip_cm=m.get("hip_cm"),
                        body_fat_percent=m.get("body_fat_percent"),
                        recorded_at=m.get("recorded_at"),
                        created_by=request.user,
                        updated_by=request.user,
                    )
        except Exception as exc:
            logger.exception("Body measurement sync upload error")
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        synced_measurements = BodyMeasurement.objects.filter(user=request.user).count()
        return Response({"synced_measurements": synced_measurements}, status=status.HTTP_200_OK)


class BodyMeasurementSyncDownloadView(BaseAPIView):
    """GET /api/backup/body-measurements/download/ — return the authenticated
    user's entire server-side body-measurement history.
    """

    permission_classes = [IsAuthenticatedUser]

    @extend_schema(tags=["Backup"])
    def get(self, request):
        measurements = BodyMeasurement.objects.filter(user=request.user).order_by("-recorded_at")

        measurements_payload = [
            {
                "age": m.age,
                "gender": m.gender,
                "is_correction": m.is_correction,
                "weight_kg": m.weight_kg,
                "height_cm": m.height_cm,
                "chest_cm": m.chest_cm,
                "waist_cm": m.waist_cm,
                "biceps_cm": m.biceps_cm,
                "thighs_cm": m.thighs_cm,
                "neck_cm": m.neck_cm,
                "hip_cm": m.hip_cm,
                "body_fat_percent": m.body_fat_percent,
                "recorded_at": m.recorded_at.isoformat(),
            }
            for m in measurements
        ]

        return Response({"measurements": measurements_payload}, status=status.HTTP_200_OK)
