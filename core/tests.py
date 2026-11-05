import tempfile
from pathlib import Path

from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from accounts.models import Gym, UserType
from accounts.tests import make_user
from core.utils import delete_if_unreferenced


class HealthCheckTest(TestCase):
    def test_health_check_returns_200(self):
        response = self.client.head("/api/health/")
        self.assertEqual(response.status_code, 200)


class DeleteIfUnreferencedTests(TestCase):
    def test_deletes_file_when_unreferenced(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "orphan.jpg").write_bytes(b"x")
            with override_settings(MEDIA_ROOT=tmp):
                delete_if_unreferenced("orphan.jpg")
                self.assertFalse(default_storage.exists("orphan.jpg"))

    def test_keeps_file_still_referenced_by_profile_picture(self):
        user = make_user("9000000500", "U@1234", user_type=UserType.MEMBER)
        user.profile_picture = "shared.jpg"
        user.save(update_fields=["profile_picture"])

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shared.jpg").write_bytes(b"x")
            with override_settings(MEDIA_ROOT=tmp):
                delete_if_unreferenced("shared.jpg")
                self.assertTrue(default_storage.exists("shared.jpg"))

    def test_keeps_file_still_referenced_by_gym_picture(self):
        Gym.objects.create(
            name="Iron Paradise", latitude="18.5", longitude="73.8",
            gym_picture="shared2.jpg",
        )

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shared2.jpg").write_bytes(b"x")
            with override_settings(MEDIA_ROOT=tmp):
                delete_if_unreferenced("shared2.jpg")
                self.assertTrue(default_storage.exists("shared2.jpg"))

    def test_deletes_file_no_longer_referenced_by_any_row(self):
        # Simulates the moment right after a replacing save has already
        # committed: the row that used to hold "old.jpg" now holds
        # something else, so no row references "old.jpg" any more.
        user = make_user("9000000501", "U2@1234", user_type=UserType.MEMBER)
        user.profile_picture = "new.jpg"
        user.save(update_fields=["profile_picture"])

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "old.jpg").write_bytes(b"x")
            with override_settings(MEDIA_ROOT=tmp):
                delete_if_unreferenced("old.jpg")
                self.assertFalse(default_storage.exists("old.jpg"))

    def test_noop_for_empty_or_none_path(self):
        delete_if_unreferenced(None)
        delete_if_unreferenced("")

    def test_noop_for_already_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp):
                delete_if_unreferenced("does_not_exist.jpg")
