from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Gym, UserType
from accounts.tests import make_user
from attendance.models import Attendance

# Minimal valid 1x1 GIF — smallest payload Django's ImageField will accept.
# Pillow detects format from content, not the filename, so naming it .png
# satisfies FileUploadSerializer's extension allowlist.
_TINY_IMAGE_BYTES = (
    b"GIF87a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00ccc,\x00"
    b"\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def tiny_photo(name="photo.png"):
    return SimpleUploadedFile(name, _TINY_IMAGE_BYTES, content_type="image/png")


def upload_test_photo(client):
    """POST a tiny real image to /api/upload-file/ and return its URL — the
    checkin/checkout `photo` field now only accepts an already-uploaded
    file's URL, not a raw multipart file."""
    res = client.post(
        reverse("upload-file"), {"file": tiny_photo()}, format="multipart"
    )
    return res.json()["data"]["url"]


GYM_LAT = "18.520430"
GYM_LNG = "73.856743"
NEAR_LAT = "18.520450"  # ~2m from the gym — inside the 50m radius
FAR_LAT = "18.521430"  # ~111m from the gym — outside the 50m radius


class AttendanceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym = Gym.objects.create(name="Iron Paradise", latitude=GYM_LAT, longitude=GYM_LNG)
        self.gym_owner = make_user(
            "9000000101", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=self.gym
        )
        self.trainer = make_user(
            "9000000102", "Trainer@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        self.member = make_user(
            "9000000103", "Member@1234", user_type=UserType.MEMBER,
            gym=self.gym_owner, trainer=self.trainer,
        )

    # ── Member check-in/out ──────────────────────────────────────────────

    def test_member_checks_in_without_photo(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(res.json()["data"]["check_in_photo"])
        self.assertEqual(Attendance.objects.get().user, self.member)

    def test_member_cannot_check_out(self):
        """Members have no check-out concept — a single daily check-in is
        the whole attendance record."""
        self.client.force_authenticate(user=self.member)
        self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        res = self.client.post(
            reverse("attendance-checkout"),
            {"timestamp": "2026-01-10T10:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        attendance = Attendance.objects.get()
        self.assertIsNone(attendance.check_out)

    def test_member_cannot_check_in_twice_same_day(self):
        self.client.force_authenticate(user=self.member)
        self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:05:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already checked in today", res.json()["message"])

    def test_member_can_check_in_again_next_day(self):
        self.client.force_authenticate(user=self.member)
        self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-11T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Attendance.objects.filter(user=self.member).count(), 2)

    def test_trainer_check_out_without_check_in_fails(self):
        self.client.force_authenticate(user=self.trainer)
        res = self.client.post(
            reverse("attendance-checkout"),
            {
                "timestamp": "2026-01-10T09:00:00Z",
                "lat": NEAR_LAT,
                "lng": GYM_LNG,
                "photo": upload_test_photo(self.client),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No active check-in", res.json()["message"])

    # ── Trainer check-in/out (photo required) ────────────────────────────

    def test_trainer_checkin_without_photo_fails(self):
        self.client.force_authenticate(user=self.trainer)
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo is required", res.json()["message"])

    def test_trainer_checkin_with_photo_succeeds(self):
        self.client.force_authenticate(user=self.trainer)
        res = self.client.post(
            reverse("attendance-checkin"),
            {
                "timestamp": "2026-01-10T09:00:00Z",
                "lat": NEAR_LAT,
                "lng": GYM_LNG,
                "photo": upload_test_photo(self.client),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        photo_url = res.json()["data"]["check_in_photo"]
        self.assertIsNotNone(photo_url)
        self.assertTrue(photo_url.startswith("http"), photo_url)

    def test_trainer_checkout_without_photo_fails(self):
        self.client.force_authenticate(user=self.trainer)
        self.client.post(
            reverse("attendance-checkin"),
            {
                "timestamp": "2026-01-10T09:00:00Z",
                "lat": NEAR_LAT,
                "lng": GYM_LNG,
                "photo": upload_test_photo(self.client),
            },
            format="json",
        )
        res = self.client.post(
            reverse("attendance-checkout"),
            {"timestamp": "2026-01-10T10:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo is required", res.json()["message"])

    def test_trainer_checkout_returns_absolute_photo_url(self):
        self.client.force_authenticate(user=self.trainer)
        self.client.post(
            reverse("attendance-checkin"),
            {
                "timestamp": "2026-01-10T09:00:00Z",
                "lat": NEAR_LAT,
                "lng": GYM_LNG,
                "photo": upload_test_photo(self.client),
            },
            format="json",
        )
        res = self.client.post(
            reverse("attendance-checkout"),
            {
                "timestamp": "2026-01-10T10:00:00Z",
                "lat": NEAR_LAT,
                "lng": GYM_LNG,
                "photo": upload_test_photo(self.client),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        photo_url = res.json()["data"]["check_out_photo"]
        self.assertIsNotNone(photo_url)
        self.assertTrue(photo_url.startswith("http"), photo_url)

    # ── Geofence ──────────────────────────────────────────────────────────

    def test_checkin_outside_radius_declined(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": FAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("away from your gym", res.json()["message"])
        self.assertFalse(Attendance.objects.exists())

    def test_checkin_declined_when_gym_has_no_location(self):
        gym_no_location = Gym.objects.create(name="No Location Gym")
        owner_no_location = make_user(
            "9000000104", "Owner2@1234", user_type=UserType.GYM_OWNER,
            gym_details=gym_no_location,
        )
        member_no_location = make_user(
            "9000000105", "Member2@1234", user_type=UserType.MEMBER, gym=owner_no_location
        )
        self.client.force_authenticate(user=member_no_location)
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("no registered location", res.json()["message"])

    # ── Permissions ───────────────────────────────────────────────────────

    def test_gym_owner_cannot_check_in(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ── Listing ───────────────────────────────────────────────────────────

    def test_gym_owner_sees_all_gym_attendance(self):
        self.client.force_authenticate(user=self.member)
        self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.get(reverse("attendance-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["data"]), 1)

    def test_attendance_list_returns_absolute_photo_url(self):
        self.client.force_authenticate(user=self.trainer)
        self.client.post(
            reverse("attendance-checkin"),
            {
                "timestamp": "2026-01-10T09:00:00Z",
                "lat": NEAR_LAT,
                "lng": GYM_LNG,
                "photo": upload_test_photo(self.client),
            },
            format="json",
        )
        res = self.client.get(reverse("attendance-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        photo_url = res.json()["data"][0]["check_in_photo"]
        self.assertIsNotNone(photo_url)
        self.assertTrue(photo_url.startswith("http"), photo_url)

    def test_member_only_sees_own_attendance(self):
        other_member = make_user(
            "9000000106", "Member3@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        self.client.force_authenticate(user=other_member)
        self.client.post(
            reverse("attendance-checkin"),
            {"timestamp": "2026-01-10T09:00:00Z", "lat": NEAR_LAT, "lng": GYM_LNG},
            format="json",
        )
        self.client.force_authenticate(user=self.member)
        res = self.client.get(reverse("attendance-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["data"]), 0)
