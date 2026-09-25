from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import Gym, UserType
from accounts.tests import make_user
from notifications.models import NotificationTemplate


class NotificationTemplateViewSetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user(
            "9000000400", "Admin@1234", user_type=UserType.ADMIN,
            is_staff=True, is_superuser=True,
        )
        gym = Gym.objects.create(name="Iron Paradise", latitude="18.5", longitude="73.8")
        self.gym_owner = make_user(
            "9000000401", "Owner@1234", user_type=UserType.GYM_OWNER, gym_details=gym
        )
        other_gym = Gym.objects.create(name="Power House", latitude="19.0", longitude="72.0")
        self.other_owner = make_user(
            "9000000402", "Owner2@1234", user_type=UserType.GYM_OWNER, gym_details=other_gym
        )

        self.global_template = NotificationTemplate.objects.create(
            gym=None, title="Welcome", message="Welcome to the gym!",
            created_by=self.admin, updated_by=self.admin,
        )
        self.own_template = NotificationTemplate.objects.create(
            gym=gym, title="Own Promo", message="50% off this month",
            created_by=self.gym_owner, updated_by=self.gym_owner,
        )

    def test_gym_owner_creates_own_template(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("notification-template-list"),
            {"title": "New Template", "message": "Hello", "category": "general"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        template = NotificationTemplate.objects.get(title="New Template")
        self.assertEqual(template.gym, self.gym_owner.gym_details)
        self.assertEqual(template.created_by, self.gym_owner)

    def test_gym_owner_can_edit_own_template(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("notification-template-update", kwargs={"pk": str(self.own_template.uuid)}),
            {"title": "Updated Promo"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.own_template.refresh_from_db()
        self.assertEqual(self.own_template.title, "Updated Promo")

    def test_gym_owner_can_delete_own_template(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.delete(
            reverse("notification-template-detail", kwargs={"pk": str(self.own_template.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.own_template.refresh_from_db()
        self.assertTrue(self.own_template.is_deleted)

    def test_gym_owner_cannot_edit_global_template(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.put(
            reverse("notification-template-detail", kwargs={"pk": str(self.global_template.uuid)}),
            {"title": "Hijacked", "message": "Hijacked", "category": "general"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.global_template.refresh_from_db()
        self.assertEqual(self.global_template.title, "Welcome")

    def test_gym_owner_cannot_partial_update_global_template(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.post(
            reverse("notification-template-update", kwargs={"pk": str(self.global_template.uuid)}),
            {"title": "Hijacked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.global_template.refresh_from_db()
        self.assertEqual(self.global_template.title, "Welcome")

    def test_gym_owner_cannot_delete_global_template(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.delete(
            reverse("notification-template-detail", kwargs={"pk": str(self.global_template.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.global_template.refresh_from_db()
        self.assertFalse(self.global_template.is_deleted)

    def test_gym_owner_cannot_edit_another_gyms_template(self):
        self.client.force_authenticate(user=self.other_owner)
        res = self.client.post(
            reverse("notification-template-update", kwargs={"pk": str(self.own_template.uuid)}),
            {"title": "Hijacked"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_gym_owner_still_sees_global_template_in_list(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.get(reverse("notification-template-list"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        titles = {t["title"] for t in res.json()["data"]}
        self.assertIn("Welcome", titles)
        self.assertIn("Own Promo", titles)

    def test_gym_owner_still_sees_global_template_on_retrieve(self):
        self.client.force_authenticate(user=self.gym_owner)
        res = self.client.get(
            reverse("notification-template-detail", kwargs={"pk": str(self.global_template.uuid)})
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_admin_can_edit_global_template(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("notification-template-update", kwargs={"pk": str(self.global_template.uuid)}),
            {"title": "Admin Updated"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_admin_can_edit_gym_owners_template(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            reverse("notification-template-update", kwargs={"pk": str(self.own_template.uuid)}),
            {"title": "Admin Updated"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
