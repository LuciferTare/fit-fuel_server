from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Gym, UserType
from accounts.tests import make_user
from attendance.models import Attendance
from backup.models import ExerciseSet, SessionExercise, SessionRestBreak, WorkoutSession


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
        )

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
