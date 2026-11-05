import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomUser, Gym, Membership, Payment, UserStatus, UserType
from accounts.utils import calculate_membership_end


def make_user(phone, password, user_type=UserType.MEMBER, status_=UserStatus.ACTIVE, **kwargs):
    return CustomUser.objects.create_user(
        phone_number=phone,
        password=password,
        user_type=user_type,
        status=status_,
        **kwargs,
    )


class AuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000001", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.gym_owner = make_user("9000000002", "Owner@1234", user_type=UserType.GYM_OWNER)

    def test_login_success(self):
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000001", "password": "Admin@1234"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.json()["data"])
        self.assertIn("refresh", res.json()["data"])
        self.assertIn("user", res.json()["data"])

    def test_login_invalid_credentials(self):
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000001", "password": "wrong"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_disabled_user(self):
        make_user("9000000010", "Pass@1234", status_=UserStatus.DISABLED)
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000010", "password": "Pass@1234"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json()["message"], "Account is disabled.")

    def test_login_suspended_user(self):
        make_user("9000000011", "Pass@1234", status_=UserStatus.SUSPENDED)
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000011", "password": "Pass@1234"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json()["message"], "Account is suspended.")

    def test_login_deleted_user(self):
        deleted = make_user("9000000012", "Pass@1234")
        deleted.soft_delete()
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000012", "password": "Pass@1234"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json()["message"], "Account has been deleted.")

    def test_login_wrong_password_on_disabled_user_does_not_leak_status(self):
        """A wrong password must look identical whether the account is
        disabled or doesn't exist — status is only revealed once the
        password has already been confirmed correct."""
        make_user("9000000013", "Pass@1234", status_=UserStatus.DISABLED)
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000013", "password": "WrongPass@1"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json()["message"], "Invalid phone number or password.")

    def test_login_wrong_password_on_suspended_user_does_not_leak_status(self):
        make_user("9000000014", "Pass@1234", status_=UserStatus.SUSPENDED)
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000014", "password": "WrongPass@1"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json()["message"], "Invalid phone number or password.")

    def test_login_wrong_password_on_deleted_user_does_not_leak_status(self):
        deleted = make_user("9000000015", "Pass@1234")
        deleted.soft_delete()
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000015", "password": "WrongPass@1"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json()["message"], "Invalid phone number or password.")

    def test_logout_success(self):
        refresh = RefreshToken.for_user(self.admin)
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("auth-logout"), {"refresh": str(refresh)}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_logout_invalid_token(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("auth-logout"), {"refresh": "bad.token"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_me_authenticated(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(reverse("auth-profile"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["phone_number"], self.admin.phone_number)

    def test_me_includes_gym_uuid_for_gym_owner(self):
        gym = Gym.objects.create(name="Iron Paradise")
        self.gym_owner.gym_details = gym
        self.gym_owner.save(update_fields=["gym_details"])

        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.get(reverse("auth-profile"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["gym_uuid"], str(gym.uuid))

    def test_me_gym_uuid_null_for_non_gym_owner(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(reverse("auth-profile"))
        self.assertIsNone(res.json()["data"]["gym_uuid"])

    def test_me_unauthenticated(self):
        res = self.client.get(reverse("auth-profile"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_success(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("auth-change-password"),
            {"old_password": "Owner@1234", "new_password": "NewOwner@9999"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_change_password_wrong_old(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("auth-change-password"),
            {"old_password": "wrong", "new_password": "NewOwner@9999"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_update_deletes_replaced_picture_but_keeps_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "old.jpg").write_bytes(b"x")
            (Path(tmp) / "new.jpg").write_bytes(b"y")
            with override_settings(MEDIA_ROOT=tmp):
                self.gym_owner.profile_picture = "old.jpg"
                self.gym_owner.save(update_fields=["profile_picture"])

                self.client.force_authenticate(user=self.gym_owner)
                res = self.client.post(
                    reverse("auth-profile-update"),
                    {"profile_picture": f"http://testserver{settings.MEDIA_URL}new.jpg"},
                    format="json",
                )
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                self.assertFalse(default_storage.exists("old.jpg"))
                self.assertTrue(default_storage.exists("new.jpg"))

    def test_profile_update_keeps_old_picture_if_another_user_shares_it(self):
        other = make_user("9000000019", "Other@1234", user_type=UserType.GYM_OWNER)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "shared.jpg").write_bytes(b"x")
            (Path(tmp) / "new.jpg").write_bytes(b"y")
            with override_settings(MEDIA_ROOT=tmp):
                self.gym_owner.profile_picture = "shared.jpg"
                self.gym_owner.save(update_fields=["profile_picture"])
                other.profile_picture = "shared.jpg"
                other.save(update_fields=["profile_picture"])

                self.client.force_authenticate(user=self.gym_owner)
                res = self.client.post(
                    reverse("auth-profile-update"),
                    {"profile_picture": f"http://testserver{settings.MEDIA_URL}new.jpg"},
                    format="json",
                )
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                self.assertTrue(default_storage.exists("shared.jpg"))

    def test_token_refresh(self):
        refresh = RefreshToken.for_user(self.admin)
        res = self.client.post(
            reverse("auth-token-refresh"),
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.json()["data"])
        self.assertIn("refresh", res.json()["data"])


class AdminTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000001", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.client.force_authenticate(user=self.admin)

    def test_admin_creates_gym_owner(self):
        res = self.client.post(
            reverse("gym-owner-list"),
            {
                "phone_number": "9000000050",
                "password": "Owner@1234",
                "first_name": "Gym",
                "last_name": "Owner",
                "gender": "male",
                "gym_name": "Iron Paradise",
                "gym_latitude": "18.520430",
                "gym_longitude": "73.856743",
                "membership": "Monthly",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        owner = CustomUser.objects.get(phone_number="9000000050")
        self.assertEqual(owner.user_type, UserType.GYM_OWNER)
        self.assertEqual(owner.gym_details.name, "Iron Paradise")
        self.assertEqual(owner.gym_details.latitude, Decimal("18.520430"))
        self.assertEqual(owner.gym_details.longitude, Decimal("73.856743"))
        today = date.today()
        self.assertEqual(owner.membership_start, today)
        self.assertEqual(owner.membership_end, calculate_membership_end(today, "Monthly"))
        self.assertEqual(owner.membership_plan, "Monthly")

    def test_admin_creates_gym_owner_missing_gym_fields(self):
        res = self.client.post(
            reverse("gym-owner-list"),
            {
                "phone_number": "9000000055",
                "password": "Owner@1234",
                "first_name": "Gym",
                "last_name": "Owner",
                "gender": "male",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("gym_name", res.json()["data"])
        self.assertIn("gym_latitude", res.json()["data"])
        self.assertIn("gym_longitude", res.json()["data"])
        self.assertIn("membership", res.json()["data"])

    def test_gym_owner_cannot_create_gym_owner(self):
        gym_owner = make_user("9000000002", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.client.force_authenticate(user=gym_owner)
        res = self.client.post(
            reverse("gym-owner-list"),
            {
                "phone_number": "9000000051",
                "password": "Owner@1234",
                "first_name": "Gym",
                "last_name": "Owner",
                "gender": "male",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_soft_deletes_gym_owner(self):
        owner = make_user("9000000052", "Owner@1234", user_type=UserType.GYM_OWNER)
        res = self.client.delete(
            reverse("gym-owner-detail", kwargs={"pk": str(owner.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        owner.refresh_from_db()
        self.assertTrue(owner.is_deleted)
        self.assertEqual(owner.status, UserStatus.DELETED)

    def test_deleting_gym_owner_cascades_to_trainers_and_members(self):
        owner = make_user("9000000053", "Owner@1234", user_type=UserType.GYM_OWNER)
        trainer = make_user(
            "9000000054", "T@1234", user_type=UserType.TRAINER, gym=owner
        )
        member = make_user(
            "9000000055", "M@1234", user_type=UserType.MEMBER, gym=owner, trainer=trainer,
        )

        res = self.client.delete(
            reverse("gym-owner-detail", kwargs={"pk": str(owner.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        trainer.refresh_from_db()
        member.refresh_from_db()
        self.assertTrue(trainer.is_deleted)
        self.assertEqual(trainer.status, UserStatus.DELETED)
        self.assertTrue(member.is_deleted)
        self.assertEqual(member.status, UserStatus.DELETED)

    def test_deleting_gym_cascades_to_owner_trainer_and_member(self):
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        owner = make_user(
            "9000000057", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        trainer = make_user(
            "9000000058", "T@1234", user_type=UserType.TRAINER, gym=owner
        )
        member = make_user(
            "9000000059", "M@1234", user_type=UserType.MEMBER, gym=owner, trainer=trainer,
        )

        res = self.client.delete(reverse("gym-detail", kwargs={"pk": str(gym.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        owner.refresh_from_db()
        trainer.refresh_from_db()
        member.refresh_from_db()
        self.assertTrue(owner.is_deleted)
        self.assertTrue(trainer.is_deleted)
        self.assertTrue(member.is_deleted)

    def test_admin_enables_gym_owner(self):
        owner = make_user(
            "9000000056", "Owner@1234", user_type=UserType.GYM_OWNER,
            status_=UserStatus.DISABLED,
        )
        res = self.client.post(
            reverse("gym-owner-enable", kwargs={"pk": str(owner.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        owner.refresh_from_db()
        self.assertEqual(owner.status, UserStatus.ACTIVE)

    def test_disable_gym_owner_returns_absolute_profile_picture_url(self):
        owner = make_user("9000000060", "Owner@1234", user_type=UserType.GYM_OWNER)
        owner.profile_picture = "profile_pictures/test.jpg"
        owner.save(update_fields=["profile_picture"])
        res = self.client.post(reverse("gym-owner-disable", kwargs={"pk": str(owner.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        url = res.json()["data"]["profile_picture"]
        self.assertTrue(url.startswith("http"), url)

    def test_enable_gym_owner_returns_absolute_profile_picture_url(self):
        owner = make_user(
            "9000000061", "Owner@1234", user_type=UserType.GYM_OWNER,
            status_=UserStatus.DISABLED,
        )
        owner.profile_picture = "profile_pictures/test.jpg"
        owner.save(update_fields=["profile_picture"])
        res = self.client.post(reverse("gym-owner-enable", kwargs={"pk": str(owner.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        url = res.json()["data"]["profile_picture"]
        self.assertTrue(url.startswith("http"), url)

    def test_admin_lists_gym_owners(self):
        make_user("9000000053", "Owner@1234", user_type=UserType.GYM_OWNER)
        make_user("9000000054", "Owner@1234", user_type=UserType.GYM_OWNER)
        res = self.client.get(reverse("gym-owner-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.json()["data"]), 2)

    def test_admin_retrieves_gym_owner_with_trainers(self):
        owner = make_user("9000000057", "Owner@1234", user_type=UserType.GYM_OWNER)
        trainer = make_user(
            "9000000112", "T@1234", user_type=UserType.TRAINER, gym=owner,
            first_name="Priya", last_name="Nair", gender="female",
        )
        res = self.client.get(
            reverse("gym-owner-detail", kwargs={"pk": str(owner.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()["data"]
        self.assertIn("trainers", data)
        self.assertEqual(len(data["trainers"]), 1)
        trainer_data = data["trainers"][0]
        self.assertEqual(trainer_data["uuid"], str(trainer.uuid))
        self.assertEqual(trainer_data["name"], "Priya Nair")
        self.assertEqual(trainer_data["phone_number"], "9000000112")
        self.assertEqual(trainer_data["gender"], "female")
        self.assertIn("date_of_birth", trainer_data)
        self.assertIn("age", trainer_data)
        self.assertIn("created_at", trainer_data)

    def test_admin_overrides_trainer_limit(self):
        owner = make_user("9000000058", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.assertEqual(owner.trainer_limit, 5)

        res = self.client.post(
            reverse("gym-owner-update", kwargs={"pk": str(owner.uuid)}),
            {"trainer_limit": 10},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        owner.refresh_from_db()
        self.assertEqual(owner.trainer_limit, 10)

        self.client.force_authenticate(user=owner)
        for i in range(6):
            res = self.client.post(
                reverse("trainer-list"),
                {
                    "phone_number": f"90000003{i:02d}",
                    "password": "Trainer@1234",
                    "first_name": "T",
                    "last_name": str(i),
                    "gender": "male",
                },
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_admin_edits_gym_owner_phone_number(self):
        owner = make_user("9000000059", "Owner@1234", user_type=UserType.GYM_OWNER)
        res = self.client.post(
            reverse("gym-owner-update", kwargs={"pk": str(owner.uuid)}),
            {"phone_number": "9000000060"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        owner.refresh_from_db()
        self.assertEqual(owner.phone_number, "9000000060")

    def test_admin_cannot_reuse_phone_number_for_gym_owner(self):
        owner = make_user("9000000061", "Owner@1234", user_type=UserType.GYM_OWNER)
        make_user("9000000062", "Owner@1234", user_type=UserType.GYM_OWNER)
        res = self.client.post(
            reverse("gym-owner-update", kwargs={"pk": str(owner.uuid)}),
            {"phone_number": "9000000062"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        owner.refresh_from_db()
        self.assertEqual(owner.phone_number, "9000000061")


class TrainerManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym_owner = make_user("9000000002", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.other_owner = make_user("9000000009", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.client.force_authenticate(user=self.gym_owner)

    def test_create_trainer(self):
        res = self.client.post(
            reverse("trainer-list"),
            {
                "phone_number": "9000000100",
                "password": "Trainer@1234",
                "first_name": "John",
                "last_name": "Doe",
                "gender": "male",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        trainer = CustomUser.objects.get(phone_number="9000000100")
        self.assertEqual(trainer.user_type, UserType.TRAINER)
        self.assertEqual(trainer.gym, self.gym_owner)

    def test_create_trainer_duplicate_phone(self):
        make_user("9000000100", "Pass@1234", user_type=UserType.TRAINER, gym=self.gym_owner)
        res = self.client.post(
            reverse("trainer-list"),
            {
                "phone_number": "9000000100",
                "password": "Trainer@1234",
                "first_name": "Dup",
                "last_name": "User",
                "gender": "male",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_default_trainer_limit_is_five(self):
        self.assertEqual(self.gym_owner.trainer_limit, 5)

    def test_create_trainer_rejected_once_limit_reached(self):
        for i in range(5):
            make_user(
                f"90000001{i:02d}", "T@1234",
                user_type=UserType.TRAINER, gym=self.gym_owner,
            )
        res = self.client.post(
            reverse("trainer-list"),
            {
                "phone_number": "9000000199",
                "password": "Trainer@1234",
                "first_name": "Sixth",
                "last_name": "Trainer",
                "gender": "male",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("trainer_limit", res.json()["data"])

    def test_list_trainers_excludes_soft_deleted(self):
        active = make_user(
            "9000000101", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        deleted = make_user(
            "9000000102", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        deleted.soft_delete(deleted_by=self.gym_owner)

        res = self.client.get(reverse("trainer-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        uuids = {t["uuid"] for t in res.json()["data"]}
        self.assertIn(str(active.uuid), uuids)
        self.assertNotIn(str(deleted.uuid), uuids)

    def test_soft_deleted_trainers_excluded_from_limit(self):
        trainers = [
            make_user(
                f"90000002{i:02d}", "T@1234",
                user_type=UserType.TRAINER, gym=self.gym_owner,
            )
            for i in range(5)
        ]
        trainers[0].soft_delete(deleted_by=self.gym_owner)

        res = self.client.post(
            reverse("trainer-list"),
            {
                "phone_number": "9000000299",
                "password": "Trainer@1234",
                "first_name": "Replacement",
                "last_name": "Trainer",
                "gender": "male",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_disable_trainer(self):
        trainer = make_user(
            "9000000110", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        res = self.client.post(
            reverse("trainer-disable", kwargs={"pk": str(trainer.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        trainer.refresh_from_db()
        self.assertEqual(trainer.status, UserStatus.DISABLED)

    def test_disable_trainer_returns_absolute_profile_picture_url(self):
        trainer = make_user(
            "9000000112", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        trainer.profile_picture = "profile_pictures/test.jpg"
        trainer.save(update_fields=["profile_picture"])
        res = self.client.post(
            reverse("trainer-disable", kwargs={"pk": str(trainer.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        url = res.json()["data"]["profile_picture"]
        self.assertTrue(url.startswith("http"), url)

    def test_trainer_update_deletes_replaced_picture(self):
        trainer = make_user(
            "9000000113", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "old.jpg").write_bytes(b"x")
            (Path(tmp) / "new.jpg").write_bytes(b"y")
            with override_settings(MEDIA_ROOT=tmp):
                trainer.profile_picture = "old.jpg"
                trainer.save(update_fields=["profile_picture"])

                res = self.client.post(
                    reverse("trainer-update", kwargs={"pk": str(trainer.uuid)}),
                    {"profile_picture": f"http://testserver{settings.MEDIA_URL}new.jpg"},
                    format="json",
                )
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                self.assertFalse(default_storage.exists("old.jpg"))
                self.assertTrue(default_storage.exists("new.jpg"))

    def test_enable_trainer(self):
        trainer = make_user(
            "9000000111", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner,
            status_=UserStatus.DISABLED,
        )
        res = self.client.post(
            reverse("trainer-enable", kwargs={"pk": str(trainer.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        trainer.refresh_from_db()
        self.assertEqual(trainer.status, UserStatus.ACTIVE)

    def test_update_trainer(self):
        trainer = make_user(
            "9000000120", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        res = self.client.post(
            reverse("trainer-update", kwargs={"pk": str(trainer.uuid)}),
            {"first_name": "UpdatedName"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        trainer.refresh_from_db()
        self.assertEqual(trainer.first_name, "UpdatedName")

    def test_soft_delete_trainer(self):
        trainer = make_user(
            "9000000130", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        res = self.client.delete(
            reverse("trainer-detail", kwargs={"pk": str(trainer.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        trainer.refresh_from_db()
        self.assertTrue(trainer.is_deleted)
        self.assertEqual(trainer.status, UserStatus.DELETED)

    def test_deleting_trainer_unassigns_members_without_deleting_them(self):
        trainer = make_user(
            "9000000131", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        member = make_user(
            "9000000132", "M@1234", user_type=UserType.MEMBER,
            gym=self.gym_owner, trainer=trainer,
        )
        res = self.client.delete(
            reverse("trainer-detail", kwargs={"pk": str(trainer.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        member.refresh_from_db()
        self.assertIsNone(member.trainer)
        self.assertFalse(member.is_deleted)
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_list_trainers_own_gym_only(self):
        make_user("9000000101", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner)
        make_user("9000000102", "T@1234", user_type=UserType.TRAINER, gym=self.other_owner)
        res = self.client.get(reverse("trainer-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        phones = [u["phone_number"] for u in res.json()["data"]]
        self.assertIn("9000000101", phones)
        self.assertNotIn("9000000102", phones)

    def test_member_cannot_create_trainer(self):
        member = make_user("9000000200", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner)
        self.client.force_authenticate(user=member)
        res = self.client.post(
            reverse("trainer-list"),
            {"phone_number": "9000000300", "password": "T@1234", "first_name": "X"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class MemberManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym_owner = make_user("9000000002", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.trainer = make_user(
            "9000000003", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        self.client.force_authenticate(user=self.gym_owner)

    def test_create_member(self):
        res = self.client.post(
            reverse("member-list"),
            {
                "phone_number": "9000000200",
                "password": "Member@1234",
                "first_name": "Jane",
                "last_name": "Smith",
                "gender": "female",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        member = CustomUser.objects.get(phone_number="9000000200")
        self.assertEqual(member.user_type, UserType.MEMBER)
        self.assertEqual(member.gym, self.gym_owner)

    def test_assign_trainer(self):
        member = make_user(
            "9000000201", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        res = self.client.post(
            reverse("member-assign-trainer", kwargs={"pk": str(member.uuid)}),
            {"trainer_uuid": str(self.trainer.uuid)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member.refresh_from_db()
        self.assertEqual(member.trainer, self.trainer)

    def test_assign_trainer_returns_absolute_profile_picture_url(self):
        member = make_user(
            "9000000203", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        member.profile_picture = "profile_pictures/test.jpg"
        member.save(update_fields=["profile_picture"])
        res = self.client.post(
            reverse("member-assign-trainer", kwargs={"pk": str(member.uuid)}),
            {"trainer_uuid": str(self.trainer.uuid)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        url = res.json()["data"]["profile_picture"]
        self.assertTrue(url.startswith("http"), url)

    def test_create_member_duplicate_phone(self):
        make_user("9000000200", "Pass@1234", user_type=UserType.MEMBER, gym=self.gym_owner)
        res = self.client.post(
            reverse("member-list"),
            {
                "phone_number": "9000000200",
                "password": "Member@1234",
                "first_name": "Dup",
                "last_name": "User",
                "gender": "female",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_disable_member(self):
        member = make_user(
            "9000000210", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        res = self.client.post(
            reverse("member-disable", kwargs={"pk": str(member.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member.refresh_from_db()
        self.assertEqual(member.status, UserStatus.DISABLED)

    def test_disable_member_returns_absolute_profile_picture_url(self):
        member = make_user(
            "9000000212", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        member.profile_picture = "profile_pictures/test.jpg"
        member.save(update_fields=["profile_picture"])
        res = self.client.post(
            reverse("member-disable", kwargs={"pk": str(member.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        url = res.json()["data"]["profile_picture"]
        self.assertTrue(url.startswith("http"), url)

    def test_enable_member(self):
        member = make_user(
            "9000000211", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner,
            status_=UserStatus.DISABLED,
        )
        res = self.client.post(
            reverse("member-enable", kwargs={"pk": str(member.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member.refresh_from_db()
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_update_member(self):
        member = make_user(
            "9000000220", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        res = self.client.post(
            reverse("member-update", kwargs={"pk": str(member.uuid)}),
            {"first_name": "UpdatedMember"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member.refresh_from_db()
        self.assertEqual(member.first_name, "UpdatedMember")

    def test_soft_delete_member(self):
        member = make_user(
            "9000000230", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        res = self.client.delete(
            reverse("member-detail", kwargs={"pk": str(member.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        member.refresh_from_db()
        self.assertTrue(member.is_deleted)
        self.assertEqual(member.status, UserStatus.DELETED)

    def test_assign_trainer_cross_gym_denied(self):
        other_owner = make_user("9000000009", "O@1234", user_type=UserType.GYM_OWNER)
        other_trainer = make_user(
            "9000000080", "T@1234", user_type=UserType.TRAINER, gym=other_owner
        )
        member = make_user(
            "9000000202", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        res = self.client.post(
            reverse("member-assign-trainer", kwargs={"pk": str(member.uuid)}),
            {"trainer_uuid": str(other_trainer.uuid)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_member_ignores_client_supplied_gym(self):
        other_owner = make_user("9000000010", "O@1234", user_type=UserType.GYM_OWNER)
        res = self.client.post(
            reverse("member-list"),
            {
                "phone_number": "9000000203",
                "password": "Member@1234",
                "first_name": "Sneaky",
                "last_name": "Client",
                "gender": "female",
                "gym": str(other_owner.uuid),
                "gym_id": str(other_owner.uuid),
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        member = CustomUser.objects.get(phone_number="9000000203")
        self.assertEqual(member.gym, self.gym_owner)

    def test_list_members_excludes_soft_deleted(self):
        active = make_user(
            "9000000240", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        deleted = make_user(
            "9000000241", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        deleted.soft_delete(deleted_by=self.gym_owner)

        res = self.client.get(reverse("member-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        uuids = {m["uuid"] for m in res.json()["data"]}
        self.assertIn(str(active.uuid), uuids)
        self.assertNotIn(str(deleted.uuid), uuids)

    def test_update_member_from_another_gym_returns_generic_404(self):
        other_owner = make_user("9000000011", "O@1234", user_type=UserType.GYM_OWNER)
        other_member = make_user(
            "9000000242", "M@1234", user_type=UserType.MEMBER, gym=other_owner
        )
        res = self.client.post(
            reverse("member-update", kwargs={"pk": str(other_member.uuid)}),
            {"first_name": "Hijacked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("deleted", res.json()["message"].lower())
        other_member.refresh_from_db()
        self.assertEqual(other_member.first_name, "")

    def test_update_soft_deleted_member_returns_specific_error(self):
        member = make_user(
            "9000000243", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        member.soft_delete(deleted_by=self.gym_owner)

        res = self.client.post(
            reverse("member-update", kwargs={"pk": str(member.uuid)}),
            {"first_name": "ShouldNotApply"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("deleted", res.json()["message"].lower())
        member.refresh_from_db()
        self.assertEqual(member.first_name, "")


class TrainerPanelTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym_owner = make_user("9000000002", "O@1234", user_type=UserType.GYM_OWNER)
        self.trainer = make_user(
            "9000000003", "T@1234", user_type=UserType.TRAINER, gym=self.gym_owner
        )
        self.member = make_user(
            "9000000004", "M@1234",
            user_type=UserType.MEMBER,
            gym=self.gym_owner,
            trainer=self.trainer,
        )
        self.unassigned = make_user(
            "9000000005", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        self.client.force_authenticate(user=self.trainer)

    def test_trainer_sees_only_assigned_members(self):
        res = self.client.get(reverse("trainer-member-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        phones = [u["phone_number"] for u in res.json()["data"]]
        self.assertIn("9000000004", phones)
        self.assertNotIn("9000000005", phones)


class MemberProfileTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym_owner = make_user("9000000002", "O@1234", user_type=UserType.GYM_OWNER)
        self.member = make_user(
            "9000000004", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        self.client.force_authenticate(user=self.member)

    def test_member_can_get_own_profile(self):
        res = self.client.get(reverse("member-profile"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["phone_number"], self.member.phone_number)

    def test_member_can_update_name(self):
        res = self.client.post(
            reverse("member-profile"), {"first_name": "Updated"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Updated")

    def test_gym_owner_cannot_access_member_panel(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.get(reverse("member-profile"))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_can_update_experience_level(self):
        res = self.client.post(
            reverse("member-profile"),
            {"experience_level": "Intermediate"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["experience_level"], "Intermediate")
        self.member.refresh_from_db()
        self.assertEqual(self.member.experience_level, "Intermediate")


class GymMasterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000006", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.member = make_user("9000000007", "M@1234", user_type=UserType.MEMBER)
        self.gym = Gym.objects.create(name="Iron Paradise")
        self.other_gym = Gym.objects.create(name="Power House")
        self.gym_owner = make_user(
            "9000000008", "Owner@1234", user_type=UserType.GYM_OWNER,
            gym_details=self.gym,
        )

    def test_admin_creates_gym(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("gym-list"),
            {"name": "New Gym", "latitude": "18.520430", "longitude": "73.856743"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Gym.objects.filter(name="New Gym").exists())

    def test_admin_creates_gym_missing_location(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(reverse("gym-list"), {"name": "No Location Gym"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", res.json()["data"])
        self.assertIn("longitude", res.json()["data"])

    def test_admin_edits_gym(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("gym-update", kwargs={"pk": str(self.gym.uuid)}),
            {"name": "Renamed Gym"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.name, "Renamed Gym")

    def test_non_admin_cannot_create_gym(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.post(reverse("gym-list"), {"name": "Power House"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_any_authenticated_user_can_list_gyms(self):
        self.client.force_authenticate(user=self.member)
        res = self.client.get(reverse("gym-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [g["name"] for g in res.json()["data"]]
        self.assertIn("Iron Paradise", names)

    def test_admin_can_reenable_deleted_gym(self):
        self.gym.soft_delete()
        self.client.force_authenticate(user=self.admin)

        res = self.client.get(reverse("gym-list"))
        names = [g["name"] for g in res.json()["data"]]
        self.assertNotIn("Iron Paradise", names)

        res = self.client.post(reverse("gym-enable", kwargs={"pk": str(self.gym.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.gym.refresh_from_db()
        self.assertFalse(self.gym.is_deleted)
        self.assertIsNone(self.gym.deleted_at)

    def test_reenable_gym_returns_absolute_gym_picture_url(self):
        self.gym.gym_picture = "gym_pictures/test.jpg"
        self.gym.save(update_fields=["gym_picture"])
        self.gym.soft_delete()
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(reverse("gym-enable", kwargs={"pk": str(self.gym.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        url = res.json()["data"]["gym_picture"]
        self.assertTrue(url.startswith("http"), url)

    def test_non_admin_cannot_reenable_gym(self):
        self.gym.soft_delete()
        self.client.force_authenticate(user=self.member)
        res = self.client.post(reverse("gym-enable", kwargs={"pk": str(self.gym.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_list_gyms(self):
        res = self.client.get(reverse("gym-list"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gym_owner_edits_own_gym(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("gym-update", kwargs={"pk": str(self.gym.uuid)}),
            {"name": "Iron Paradise Renamed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.name, "Iron Paradise Renamed")

    def test_gym_owner_can_update_own_gym_location(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("gym-update", kwargs={"pk": str(self.gym.uuid)}),
            {"latitude": "19.076090", "longitude": "72.877426"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.latitude, Decimal("19.076090"))
        self.assertEqual(self.gym.longitude, Decimal("72.877426"))

    def test_gym_owner_cannot_clear_gym_location(self):
        self.gym.latitude = Decimal("18.520430")
        self.gym.longitude = Decimal("73.856743")
        self.gym.save(update_fields=["latitude", "longitude"])

        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("gym-update", kwargs={"pk": str(self.gym.uuid)}),
            {"latitude": None, "longitude": None},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.gym.refresh_from_db()
        self.assertEqual(self.gym.latitude, Decimal("18.520430"))

    def test_gym_owner_cannot_edit_another_gym(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("gym-update", kwargs={"pk": str(self.other_gym.uuid)}),
            {"name": "Hijacked Name"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.other_gym.refresh_from_db()
        self.assertEqual(self.other_gym.name, "Power House")

    def test_gym_owner_cannot_create_gym(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(reverse("gym-list"), {"name": "New Gym"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_gym_owner_cannot_delete_gym(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.delete(reverse("gym-detail", kwargs={"pk": str(self.gym.uuid)}))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class MemberPaymentViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.owner = make_user(
            "9000000330", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.member = make_user(
            "9000000331", "Member@1234", user_type=UserType.MEMBER, gym=self.owner
        )
        self.client.force_authenticate(user=self.owner)

    def payload(self, **overrides):
        data = {
            "member_id": str(self.member.uuid),
            "date": "2026-06-30",
            "amount": "1500.00",
            "mode": "cash",
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "plan": "Monthly",
        }
        data.update(overrides)
        return data

    def test_creates_membership_and_payment(self):
        res = self.client.post(reverse("member-payment"), self.payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        membership = Membership.objects.get(member=self.member)
        self.assertEqual(membership.amount_paid, Decimal("1500.00"))

        payment = Payment.objects.get(membership=membership)
        self.assertEqual(payment.paid_by, self.member)
        self.assertEqual(payment.amount, Decimal("1500.00"))
        self.assertEqual(payment.mode, "cash")
        self.assertEqual(payment.paid_on.date(), date(2026, 6, 30))

    def test_response_date_echoes_submitted_date_not_start_date(self):
        res = self.client.post(reverse("member-payment"), self.payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        body = res.json()["data"]
        self.assertEqual(body["date"], "2026-06-30")
        self.assertEqual(body["start_date"], "2026-07-01")
        self.assertEqual(body["amount"], "1500.00")

    def test_payment_appears_in_payments_list(self):
        self.client.post(reverse("member-payment"), self.payload(), format="json")
        res = self.client.get(reverse("payment-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()["data"]), 1)
        self.assertEqual(res.json()["data"][0]["payment_date"], "2026-06-30")


class AccountRevocationTests(TestCase):
    """Covers that an already-issued JWT stops working the moment the
    account is disabled/suspended/soft-deleted or the password changes, and
    that logout can't blacklist a token belonging to a different user."""

    def setUp(self):
        self.client = APIClient()
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.owner = make_user(
            "9000000340", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.member = make_user(
            "9000000341", "Member@1234", user_type=UserType.MEMBER, gym=self.owner
        )

    def authenticate_as(self, user):
        access = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_disabling_user_revokes_existing_access_token(self):
        self.authenticate_as(self.member)
        self.assertEqual(self.client.get(reverse("auth-profile")).status_code, status.HTTP_200_OK)

        self.member.status = UserStatus.DISABLED
        self.member.save(update_fields=["status"])

        res = self.client.get(reverse("auth-profile"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_soft_delete_revokes_existing_access_token(self):
        self.authenticate_as(self.member)
        self.assertEqual(self.client.get(reverse("auth-profile")).status_code, status.HTTP_200_OK)

        self.member.soft_delete(deleted_by=self.owner)

        res = self.client.get(reverse("auth-profile"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_change_password_revokes_existing_access_token(self):
        self.authenticate_as(self.member)
        self.assertEqual(self.client.get(reverse("auth-profile")).status_code, status.HTTP_200_OK)

        self.member.set_password("NewPass@9999")
        self.member.save(update_fields=["password"])

        res = self.client.get(reverse("auth-profile"))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rejects_token_not_belonging_to_caller(self):
        other_refresh = RefreshToken.for_user(self.member)
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(
            reverse("auth-logout"), {"refresh": str(other_refresh)}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Still usable — proves it was never blacklisted.
        res = self.client.post(
            reverse("auth-token-refresh"), {"refresh": str(other_refresh)}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_logout_own_token_succeeds(self):
        own_refresh = RefreshToken.for_user(self.owner)
        self.client.force_authenticate(user=self.owner)

        res = self.client.post(
            reverse("auth-logout"), {"refresh": str(own_refresh)}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class MembershipViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.gym_owner = make_user("9000000350", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.other_owner = make_user("9000000351", "Owner@1234", user_type=UserType.GYM_OWNER)
        self.member = make_user(
            "9000000352", "M@1234", user_type=UserType.MEMBER, gym=self.gym_owner
        )
        self.other_member = make_user(
            "9000000353", "M@1234", user_type=UserType.MEMBER, gym=self.other_owner
        )
        self.client.force_authenticate(user=self.gym_owner)

    def payload(self, member, **overrides):
        data = {
            "member": str(member.uuid),
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "plan": "Monthly",
            "amount_paid": "1500.00",
            "payment_mode": "cash",
        }
        data.update(overrides)
        return data

    def test_create_membership_for_own_member_succeeds(self):
        res = self.client.post(
            reverse("membership-list"), self.payload(self.member), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Membership.objects.filter(member=self.member).exists())

    def test_create_membership_for_other_gym_member_denied(self):
        res = self.client.post(
            reverse("membership-list"), self.payload(self.other_member), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Membership.objects.filter(member=self.other_member).exists())

    def test_create_membership_for_soft_deleted_member_denied(self):
        self.member.soft_delete(deleted_by=self.gym_owner)
        res = self.client.post(
            reverse("membership-list"), self.payload(self.member), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Membership.objects.filter(member=self.member).exists())

    def test_reassign_membership_to_other_gym_member_denied(self):
        membership = Membership.objects.create(
            member=self.member,
            start_date="2026-06-01",
            end_date="2026-06-30",
            amount_paid="1500.00",
            payment_mode="cash",
            created_by=self.gym_owner,
            updated_by=self.gym_owner,
        )
        res = self.client.post(
            reverse("membership-update", kwargs={"pk": str(membership.uuid)}),
            {"member": str(self.other_member.uuid)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        membership.refresh_from_db()
        self.assertEqual(membership.member, self.member)
