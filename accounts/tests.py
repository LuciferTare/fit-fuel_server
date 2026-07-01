from datetime import date

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomUser, UserStatus, UserType
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

    def test_login_suspended_user(self):
        make_user("9000000011", "Pass@1234", status_=UserStatus.SUSPENDED)
        res = self.client.post(
            reverse("auth-login"),
            {"phone_number": "9000000011", "password": "Pass@1234"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

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
        res = self.client.get(reverse("auth-me"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["phone_number"], self.admin.phone_number)

    def test_me_unauthenticated(self):
        res = self.client.get(reverse("auth-me"))
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
                "gender": "MALE",
                "gym_name": "Iron Paradise",
                "membership": "Monthly",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        owner = CustomUser.objects.get(phone_number="9000000050")
        self.assertEqual(owner.user_type, UserType.GYM_OWNER)
        self.assertEqual(owner.gym_details.name, "Iron Paradise")
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
                "gender": "MALE",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("gym_name", res.json()["data"])
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
                "gender": "MALE",
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

    def test_admin_lists_gym_owners(self):
        make_user("9000000053", "Owner@1234", user_type=UserType.GYM_OWNER)
        make_user("9000000054", "Owner@1234", user_type=UserType.GYM_OWNER)
        res = self.client.get(reverse("gym-owner-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(res.json()["data"]), 2)


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
                "gender": "MALE",
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
                "gender": "MALE",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

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
                "gender": "FEMALE",
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

    def test_create_member_duplicate_phone(self):
        make_user("9000000200", "Pass@1234", user_type=UserType.MEMBER, gym=self.gym_owner)
        res = self.client.post(
            reverse("member-list"),
            {
                "phone_number": "9000000200",
                "password": "Member@1234",
                "first_name": "Dup",
                "last_name": "User",
                "gender": "FEMALE",
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
