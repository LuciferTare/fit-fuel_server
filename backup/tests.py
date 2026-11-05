from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Gym, UserType
from accounts.tests import make_user
from attendance.models import Attendance
from attendance.tests import FAR_LAT, GYM_LAT, GYM_LNG, NEAR_LAT, upload_test_photo
from backup.models import (
    BodyMeasurement,
    ExerciseSet,
    SessionExercise,
    SessionRestBreak,
    WorkoutSession,
)


class BackupDownloadViewTests(TestCase):
    """Covers the Attendance.member -> Attendance.user rename this view's
    ?user_id= filter relies on."""

    def setUp(self):
        self.client = APIClient()
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.owner = make_user(
            "9000000301", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.member = make_user(
            "9000000302", "Member@1234", user_type=UserType.MEMBER, gym=self.owner
        )
        Attendance.objects.create(
            user=self.member,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat="18.5",
            check_in_lng="73.8",
            check_in_photo="attendance_photos/test.jpg",
        )

    def test_download_returns_absolute_photo_url(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(reverse("backup-download"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        photo_url = res.json()["data"]["changes"]["attendance"][0]["check_in_photo"]
        self.assertIsNotNone(photo_url)
        self.assertTrue(photo_url.startswith("http"), photo_url)

    def test_download_filters_by_user_id(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(
            reverse("backup-download"), {"user_id": str(self.member.uuid)}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["data"]["changes"]["attendance"]), 1)

    def test_download_filters_out_other_users(self):
        other = make_user(
            "9000000303", "Other@1234", user_type=UserType.MEMBER, gym=self.owner
        )
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(reverse("backup-download"), {"user_id": str(other.uuid)})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["data"]["changes"]["attendance"]), 0)

    def test_download_scopes_gym_owner_to_own_gym(self):
        other_gym = Gym.objects.create(name="Power House", latitude="19.0", longitude="72.0")
        other_owner = make_user(
            "9000000304", "Owner2@1234", user_type=UserType.GYM_OWNER, gym_details=other_gym
        )
        other_member = make_user(
            "9000000305", "Member2@1234", user_type=UserType.MEMBER, gym=other_owner
        )
        Attendance.objects.create(
            user=other_member,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat="19.0",
            check_in_lng="72.0",
        )

        self.client.force_authenticate(user=self.owner)
        res = self.client.get(reverse("backup-download"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        rows = res.json()["data"]["changes"]["attendance"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user"], str(self.member.uuid))

    def test_download_scopes_trainer_to_own_and_assigned_members(self):
        trainer = make_user(
            "9000000306", "T@1234", user_type=UserType.TRAINER, gym=self.owner
        )
        assigned_member = make_user(
            "9000000307", "M2@1234", user_type=UserType.MEMBER, gym=self.owner, trainer=trainer,
        )
        Attendance.objects.create(
            user=assigned_member,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat="18.5",
            check_in_lng="73.8",
        )
        Attendance.objects.create(
            user=trainer,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat="18.5",
            check_in_lng="73.8",
            check_in_photo="attendance_photos/x.png",
        )
        # self.member (unassigned to `trainer`) already has an attendance row from setUp.

        self.client.force_authenticate(user=trainer)
        res = self.client.get(reverse("backup-download"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user_uuids = {row["user"] for row in res.json()["data"]["changes"]["attendance"]}
        self.assertEqual(user_uuids, {str(assigned_member.uuid), str(trainer.uuid)})
        self.assertNotIn(str(self.member.uuid), user_uuids)

    def test_download_admin_sees_every_gym(self):
        admin = make_user(
            "9000000308", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        other_gym = Gym.objects.create(name="Power House", latitude="19.0", longitude="72.0")
        other_owner = make_user(
            "9000000309", "Owner2@1234", user_type=UserType.GYM_OWNER, gym_details=other_gym
        )
        other_member = make_user(
            "9000000310", "Member2@1234", user_type=UserType.MEMBER, gym=other_owner
        )
        Attendance.objects.create(
            user=other_member,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat="19.0",
            check_in_lng="72.0",
        )

        self.client.force_authenticate(user=admin)
        res = self.client.get(reverse("backup-download"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["data"]["changes"]["attendance"]), 2)


class BackupUploadViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym = Gym.objects.create(name="Iron Paradise", latitude=GYM_LAT, longitude=GYM_LNG)
        self.owner = make_user(
            "9000000320", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=self.gym
        )
        self.trainer = make_user(
            "9000000321", "Trainer@1234", user_type=UserType.TRAINER, gym=self.owner
        )
        self.member = make_user(
            "9000000322", "Member@1234", user_type=UserType.MEMBER,
            gym=self.owner, trainer=self.trainer,
        )
        other_gym = Gym.objects.create(name="Power House", latitude="19.0", longitude="72.0")
        self.other_owner = make_user(
            "9000000323", "Owner2@1234", user_type=UserType.GYM_OWNER, gym_details=other_gym
        )
        self.other_member = make_user(
            "9000000324", "Member2@1234", user_type=UserType.MEMBER, gym=self.other_owner
        )
        self.unassigned_member = make_user(
            "9000000325", "Member3@1234", user_type=UserType.MEMBER, gym=self.owner,
        )

    def upload(self, user_id, extra=None, action="create", uuid=None):
        data = {
            "user_id": str(user_id),
            "check_in": "2026-01-10T09:00:00Z",
            "check_in_lat": NEAR_LAT,
            "check_in_lng": GYM_LNG,
        }
        if uuid:
            data["uuid"] = uuid
        if extra:
            data.update(extra)
        return self.client.post(
            reverse("backup-upload"),
            {"changes": [{"model": "attendance.Attendance", "action": action, "data": data}]},
            format="json",
        )

    def test_gym_owner_creates_attendance_for_own_member(self):
        self.client.force_authenticate(user=self.owner)
        res = self.upload(self.member.uuid)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 1)
        self.assertTrue(Attendance.objects.filter(user=self.member).exists())

    def test_gym_owner_cannot_create_attendance_for_other_gym_member(self):
        self.client.force_authenticate(user=self.owner)
        res = self.upload(self.other_member.uuid)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 0)
        self.assertEqual(len(res.json()["data"]["errors"]), 1)
        self.assertFalse(Attendance.objects.filter(user=self.other_member).exists())

    def test_trainer_creates_attendance_for_assigned_member(self):
        self.client.force_authenticate(user=self.trainer)
        res = self.upload(self.member.uuid)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 1)

    def test_trainer_cannot_create_attendance_for_unassigned_member(self):
        self.client.force_authenticate(user=self.trainer)
        res = self.upload(self.unassigned_member.uuid)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 0)
        self.assertEqual(len(res.json()["data"]["errors"]), 1)

    def test_trainer_creates_own_attendance_with_photo(self):
        self.client.force_authenticate(user=self.trainer)
        photo_url = upload_test_photo(self.client)
        res = self.upload(self.trainer.uuid, extra={"check_in_photo": photo_url})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 1)

    def test_backup_upload_rejects_trainer_checkin_without_photo(self):
        self.client.force_authenticate(user=self.trainer)
        res = self.upload(self.trainer.uuid)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 0)
        self.assertIn("photo", res.json()["data"]["errors"][0]["error"].lower())

    def test_backup_upload_rejects_member_checkin_outside_geofence(self):
        self.client.force_authenticate(user=self.owner)
        res = self.upload(self.member.uuid, extra={"check_in_lat": FAR_LAT})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 0)
        self.assertIn("away from your gym", res.json()["data"]["errors"][0]["error"])

    def test_backup_upload_rejects_duplicate_member_checkin_same_day(self):
        Attendance.objects.create(
            user=self.member,
            check_in="2026-01-10T07:00:00Z",
            check_in_lat=GYM_LAT,
            check_in_lng=GYM_LNG,
        )
        self.client.force_authenticate(user=self.owner)
        res = self.upload(self.member.uuid)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["created"], 0)
        self.assertIn("already checked in", res.json()["data"]["errors"][0]["error"])

    def test_backup_upload_cannot_reassign_attendance_owner_on_update(self):
        attendance = Attendance.objects.create(
            user=self.member,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat=GYM_LAT,
            check_in_lng=GYM_LNG,
        )
        self.client.force_authenticate(user=self.owner)
        res = self.upload(
            self.other_member.uuid,
            action="update",
            uuid=str(attendance.uuid),
            extra={"check_in_lat": NEAR_LAT, "check_in_lng": GYM_LNG},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["updated"], 1)
        attendance.refresh_from_db()
        self.assertEqual(attendance.user, self.member)


class WorkoutSyncUploadViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        owner = make_user("9000000310", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym)
        self.member = make_user("9000000311", "Member@1234", user_type=UserType.MEMBER, gym=owner)
        self.client.force_authenticate(user=self.member)

    def payload(self, session_date="2026-01-15"):
        return {
            "sessions": [
                {
                    "session_date": session_date,
                    "duration_minutes": 45,
                    "notes": "Leg day",
                    "calories_burned": 320.5,
                    "is_rest_day": False,
                    "exercises": [
                        {
                            "exercise_name": "Barbell Squat",
                            "body_part": "Legs",
                            "muscle": "Quads",
                            "is_unilateral": False,
                            "set_type": "normal",
                            "sets": [
                                {"set_number": 1, "reps": 10, "weight_kg": 60.0},
                                {"set_number": 2, "reps": 8, "weight_kg": 65.0},
                            ],
                        }
                    ],
                    "rest_breaks": [{"duration_minutes": 2, "sort_index": 0}],
                }
            ]
        }

    def test_uploads_full_nested_structure(self):
        res = self.client.post(
            reverse("backup-workouts-upload"), self.payload(), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["synced_sessions"], 1)

        session = WorkoutSession.objects.get(user=self.member)
        self.assertEqual(str(session.session_date), "2026-01-15")
        self.assertEqual(SessionExercise.objects.filter(session=session).count(), 1)
        exercise = SessionExercise.objects.get(session=session)
        self.assertEqual(ExerciseSet.objects.filter(exercise=exercise).count(), 2)
        self.assertEqual(SessionRestBreak.objects.filter(session=session).count(), 1)

    def test_second_sync_replaces_rather_than_accumulates(self):
        self.client.post(reverse("backup-workouts-upload"), self.payload("2026-01-15"), format="json")

        second_payload = self.payload("2026-01-15")
        second_payload["sessions"].append(self.payload("2026-01-16")["sessions"][0])
        res = self.client.post(
            reverse("backup-workouts-upload"), second_payload, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["synced_sessions"], 2)
        self.assertEqual(WorkoutSession.objects.filter(user=self.member).count(), 2)

    def test_sync_does_not_affect_other_users(self):
        gym = Gym.objects.create(name="Other Gym", latitude="19.0", longitude="72.0")
        owner = make_user("9000000312", "Owner2@1234", user_type=UserType.GYM_OWNER, gym_details=gym)
        other_member = make_user("9000000313", "Other@1234", user_type=UserType.MEMBER, gym=owner)
        self.client.force_authenticate(user=other_member)
        self.client.post(reverse("backup-workouts-upload"), self.payload(), format="json")

        self.client.force_authenticate(user=self.member)
        res = self.client.post(reverse("backup-workouts-upload"), self.payload(), format="json")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(WorkoutSession.objects.filter(user=other_member).count(), 1)
        self.assertEqual(WorkoutSession.objects.filter(user=self.member).count(), 1)

    def test_empty_sessions_array_is_rejected_and_keeps_history(self):
        self.client.post(reverse("backup-workouts-upload"), self.payload(), format="json")

        res = self.client.post(
            reverse("backup-workouts-upload"), {"sessions": []}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(WorkoutSession.objects.filter(user=self.member).count(), 1)

    def test_missing_sessions_key_is_rejected_and_keeps_history(self):
        self.client.post(reverse("backup-workouts-upload"), self.payload(), format="json")

        res = self.client.post(reverse("backup-workouts-upload"), {}, format="json")

        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(WorkoutSession.objects.filter(user=self.member).count(), 1)


class BodyMeasurementSyncUploadViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        owner = make_user("9000000320", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym)
        self.member = make_user("9000000321", "Member@1234", user_type=UserType.MEMBER, gym=owner)
        self.client.force_authenticate(user=self.member)

    def payload(self, recorded_at="2026-01-15T08:30:00Z"):
        return {
            "measurements": [
                {
                    "age": 28,
                    "gender": "male",
                    "is_correction": False,
                    "weight_kg": 72.5,
                    "height_cm": 178.0,
                    "recorded_at": recorded_at,
                }
            ]
        }

    def test_uploads_measurements(self):
        res = self.client.post(
            reverse("backup-body-measurements-upload"), self.payload(), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["synced_measurements"], 1)
        self.assertEqual(BodyMeasurement.objects.filter(user=self.member).count(), 1)

    def test_empty_measurements_array_is_rejected_and_keeps_history(self):
        self.client.post(
            reverse("backup-body-measurements-upload"), self.payload(), format="json"
        )

        res = self.client.post(
            reverse("backup-body-measurements-upload"), {"measurements": []}, format="json"
        )

        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(BodyMeasurement.objects.filter(user=self.member).count(), 1)

    def test_missing_measurements_key_is_rejected_and_keeps_history(self):
        self.client.post(
            reverse("backup-body-measurements-upload"), self.payload(), format="json"
        )

        res = self.client.post(reverse("backup-body-measurements-upload"), {}, format="json")

        self.assertEqual(res.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(BodyMeasurement.objects.filter(user=self.member).count(), 1)
