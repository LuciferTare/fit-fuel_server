import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Gym, Payment, PaymentMode, PaymentStatus, UserType
from accounts.tests import make_user
from attendance.models import Attendance
from backup.models import WorkoutSession
from core.models import DailyRequestCount


class InactiveMembersViewTests(TestCase):
    """Covers the Attendance.member -> Attendance.user rename this view's
    subquery relies on, and the gym-owner/trainer scoping split."""

    def setUp(self):
        self.client = APIClient()
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.owner = make_user(
            "9000000201", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.trainer = make_user(
            "9000000203", "Trainer@1234", user_type=UserType.TRAINER, gym=self.owner
        )
        self.member = make_user(
            "9000000202", "Member@1234", user_type=UserType.MEMBER,
            gym=self.owner, trainer=self.trainer,
        )

    def test_member_with_no_checkins_is_inactive(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(reverse("report-inactive-members"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member_ids = [row["member_id"] for row in res.json()["data"]]
        self.assertIn(str(self.member.uuid), member_ids)

    def test_member_with_recent_checkin_is_not_inactive(self):
        Attendance.objects.create(
            user=self.member,
            check_in="2026-01-10T09:00:00Z",
            check_in_lat="18.5",
            check_in_lng="73.8",
        )
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(f"{reverse('report-inactive-members')}?days=3650")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member_ids = [row["member_id"] for row in res.json()["data"]]
        self.assertNotIn(str(self.member.uuid), member_ids)

    def test_trainer_sees_only_own_assigned_inactive_members(self):
        other_trainer = make_user(
            "9000000204", "Trainer2@1234", user_type=UserType.TRAINER, gym=self.owner
        )
        other_member = make_user(
            "9000000205", "Member2@1234", user_type=UserType.MEMBER,
            gym=self.owner, trainer=other_trainer,
        )
        self.client.force_authenticate(user=self.trainer)
        res = self.client.get(reverse("report-inactive-members"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        member_ids = [row["member_id"] for row in res.json()["data"]]
        self.assertIn(str(self.member.uuid), member_ids)
        self.assertNotIn(str(other_member.uuid), member_ids)


class GymSubscriptionExpiryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000210", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        self.gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")

    def test_admin_sees_gym_owner_with_expiring_subscription(self):
        soon = timezone.now().date() + timezone.timedelta(days=3)
        owner = make_user(
            "9000000211", "Owner@1234", user_type=UserType.GYM_OWNER,
            gym_details=self.gym, membership_end=soon,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(reverse("report-gym-subscription-expiry"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        owner_ids = [row["gym_owner_id"] for row in res.json()["data"]]
        self.assertIn(str(owner.uuid), owner_ids)

    def test_gym_owner_cannot_access(self):
        owner = make_user(
            "9000000212", "Owner2@1234", user_type=UserType.GYM_OWNER, gym_details=self.gym
        )
        self.client.force_authenticate(user=owner)
        res = self.client.get(reverse("report-gym-subscription-expiry"))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class RevenueSummaryViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000220", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.owner = make_user(
            "9000000221", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.member = make_user(
            "9000000222", "Member@1234", user_type=UserType.MEMBER, gym=self.owner
        )
        now = timezone.now()
        Payment.objects.create(
            paid_by=self.member, amount=Decimal("1500.00"),
            mode=PaymentMode.CASH, status=PaymentStatus.PAID, paid_on=now,
        )
        Payment.objects.create(
            paid_by=self.member, amount=Decimal("500.00"),
            mode=PaymentMode.ONLINE, status=PaymentStatus.PAID, paid_on=now,
        )
        Payment.objects.create(
            paid_by=self.member, amount=Decimal("300.00"),
            mode=PaymentMode.CASH, status=PaymentStatus.PENDING, paid_on=now,
        )
        # A platform payment from the gym owner — only visible to admin.
        Payment.objects.create(
            paid_by=self.owner, amount=Decimal("9999.00"),
            mode=PaymentMode.ONLINE, status=PaymentStatus.PAID, paid_on=now,
        )

    def test_gym_owner_sees_only_their_members_revenue(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(reverse("report-revenue-summary"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()["data"]
        self.assertEqual(Decimal(str(data["total_revenue"])), Decimal("2000.00"))
        self.assertEqual(data["total_transactions"], 2)
        self.assertEqual(Decimal(str(data["pending_amount"])), Decimal("300.00"))
        methods = {row["method"]: Decimal(str(row["amount"])) for row in data["method_breakdown"]}
        self.assertEqual(methods["cash"], Decimal("1500.00"))
        self.assertEqual(methods["online"], Decimal("500.00"))

    def test_admin_sees_only_gym_owner_payments(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get(reverse("report-revenue-summary"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()["data"]
        self.assertEqual(Decimal(str(data["total_revenue"])), Decimal("9999.00"))
        self.assertEqual(data["total_transactions"], 1)


class StorageUsageViewTests(TestCase):
    def test_admin_sees_total_media_bytes(self):
        admin = make_user(
            "9000000230", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            media_root = Path(tmp)
            (media_root / "profile_pictures").mkdir()
            (media_root / "profile_pictures" / "a.jpg").write_bytes(b"x" * 100)
            (media_root / "gym_pictures").mkdir()
            (media_root / "gym_pictures" / "b.jpg").write_bytes(b"y" * 250)

            with override_settings(MEDIA_ROOT=str(media_root)):
                client = APIClient()
                client.force_authenticate(user=admin)
                res = client.get(reverse("report-storage-usage"))

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["total_bytes"], 350)

    def test_non_admin_cannot_access(self):
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        owner = make_user(
            "9000000231", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        self.client = APIClient()
        self.client.force_authenticate(user=owner)
        res = self.client.get(reverse("report-storage-usage"))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ApiRequestsTodayViewTests(TestCase):
    def test_count_reflects_requests_made_today(self):
        admin = make_user(
            "9000000240", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        client = APIClient()
        client.force_authenticate(user=admin)

        # Each authenticated call below itself increments the counter via
        # RequestCounterMiddleware, so read the baseline first.
        before = client.get(reverse("report-api-requests-today")).json()["data"]["count"]
        client.get(reverse("report-inactive-members"))
        after = client.get(reverse("report-api-requests-today")).json()["data"]["count"]
        # +1 for the inactive-members call, +1 for the "before" call itself.
        self.assertEqual(after, before + 2)

    def test_admin_ui_requests_are_not_counted(self):
        today = timezone.localdate()
        DailyRequestCount.objects.filter(date=today).delete()
        self.client.get("/admin/login/")
        self.assertFalse(DailyRequestCount.objects.filter(date=today).exists())


class WorkoutBackupsCountViewTests(TestCase):
    def setUp(self):
        self.admin = make_user(
            "9000000250", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.owner = make_user(
            "9000000251", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )

    def test_counts_distinct_users_not_sessions(self):
        member = make_user(
            "9000000252", "Member@1234", user_type=UserType.MEMBER, gym=self.owner
        )
        WorkoutSession.objects.create(user=member, session_date="2026-01-15")
        WorkoutSession.objects.create(user=member, session_date="2026-01-16")

        client = APIClient()
        client.force_authenticate(user=self.admin)
        res = client.get(reverse("report-workout-backups-count"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["data"]["count"], 1)

    def test_non_admin_cannot_access(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        res = client.get(reverse("report-workout-backups-count"))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
