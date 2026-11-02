from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    CustomUser, MembershipPlan, Membership, Payment, PaymentRequest, PaymentRequestStatus as S,
    UserType,
)
from accounts.utils import add_months


def mk(phone, user_type, **kw):
    return CustomUser.objects.create_user(phone_number=phone, password="Pass@1234", user_type=user_type, **kw)


class UpiFlowTests(TestCase):
    def setUp(self):
        self.admin = mk("9100000001", UserType.ADMIN, payment_upi_id="admin@okbank", payment_payee_name="Fit&Fuel")
        self.owner = mk("9100000002", UserType.GYM_OWNER, payment_upi_id="gym@okbank", payment_payee_name="Iron Gym")
        self.member = mk("9100000003", UserType.MEMBER, gym=self.owner)
        self.other_owner = mk("9100000004", UserType.GYM_OWNER, payment_upi_id="x@okbank")
        self.plan = MembershipPlan.objects.create(provider=self.owner, name="Monthly", amount="1500.00", duration_months=1)
        self.admin_plan = MembershipPlan.objects.create(provider=self.admin, name="Pro", amount="999.00", duration_months=12)

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def request_for(self, payer=None, plan=None):
        res = self.api(payer or self.member).post(
            "/api/payment-requests/", {"plan_id": str((plan or self.plan).uuid)}, format="json"
        )
        return res

    def submit(self, uuid, payer=None):
        return self.api(payer or self.member).post(f"/api/payment-requests/{uuid}/submit/", {"utr": "123456789012"}, format="json")

    def test_member_flow_verify_once_activates_membership(self):
        res = self.request_for()
        self.assertEqual(res.status_code, 201)
        uuid = res.json()["data"]["uuid"]
        self.assertEqual(self.request_for().status_code, 200)  # reused, not duplicated
        self.assertEqual(PaymentRequest.objects.count(), 1)

        self.assertEqual(self.submit(uuid).json()["data"]["status"], "submitted")
        self.member.refresh_from_db()
        self.assertIsNone(self.member.membership_end)  # submitting grants nothing
        self.assertEqual(self.api(self.owner).get("/api/payment-requests/incoming-count/").json()["data"]["count"], 1)

        for _ in range(2):  # second call is idempotent
            res = self.api(self.owner).post(f"/api/payment-requests/{uuid}/verify/")
            self.assertEqual(res.json()["data"]["status"], "verified")
        self.assertEqual(Membership.objects.count(), 1)
        payment = Payment.objects.get()
        self.assertEqual(payment.amount, Decimal("1500.00"))
        self.member.refresh_from_db()
        today = timezone.localdate()
        self.assertEqual(self.member.membership_start, today)
        self.assertEqual(self.member.membership_end, add_months(today, 1) - timedelta(days=1))

    def test_renewal_starts_day_after_current_end(self):
        end = timezone.localdate() + timedelta(days=10)
        self.member.membership_end = end
        self.member.save()
        uuid = self.request_for().json()["data"]["uuid"]
        self.submit(uuid)
        self.api(self.owner).post(f"/api/payment-requests/{uuid}/verify/")
        self.member.refresh_from_db()
        self.assertEqual(self.member.membership_start, end + timedelta(days=1))

    def test_only_intended_recipient_can_decide(self):
        uuid = self.request_for().json()["data"]["uuid"]
        self.submit(uuid)
        for other in (self.admin, self.other_owner, self.member):
            self.assertIn(self.api(other).post(f"/api/payment-requests/{uuid}/verify/").status_code, (403, 404))
        self.assertEqual(Payment.objects.count(), 0)

    def test_cannot_verify_unsubmitted_and_client_cannot_activate(self):
        uuid = self.request_for().json()["data"]["uuid"]
        self.assertEqual(self.api(self.owner).post(f"/api/payment-requests/{uuid}/verify/").status_code, 409)
        self.assertEqual(self.api(self.member).post(f"/api/payment-requests/{uuid}/verify/").status_code, 403)
        # client-supplied amount/status are ignored
        res = self.api(self.member).post(
            "/api/payment-requests/", {"plan_id": str(self.plan.uuid), "amount": "1", "status": "verified"}, format="json"
        )
        self.assertEqual(res.json()["data"]["amount"], "1500.00")
        self.assertEqual(res.json()["data"]["status"], "pending_payment")

    def test_reject_needs_reason_and_creates_nothing(self):
        uuid = self.request_for().json()["data"]["uuid"]
        self.submit(uuid)
        url = f"/api/payment-requests/{uuid}/reject/"
        self.assertEqual(self.api(self.owner).post(url, {}, format="json").status_code, 400)
        self.assertEqual(self.api(self.owner).post(url, {"reason": "No credit"}, format="json").json()["data"]["status"], "rejected")
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(self.api(self.owner).post(f"/api/payment-requests/{uuid}/verify/").status_code, 409)

    def test_terms_are_frozen_and_expiry_blocks_verify(self):
        uuid = self.request_for().json()["data"]["uuid"]
        self.plan.amount = Decimal("1.00")
        self.plan.save()
        self.owner.payment_upi_id = "new@okbank"
        self.owner.save()
        req = PaymentRequest.objects.get()
        self.assertEqual((req.amount, req.upi_id), (Decimal("1500.00"), "gym@okbank"))
        self.submit(uuid)
        PaymentRequest.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.api(self.owner).post(f"/api/payment-requests/{uuid}/verify/").status_code, 409)
        self.assertEqual(PaymentRequest.objects.get().status, S.EXPIRED)
        self.assertEqual(Payment.objects.count(), 0)

    def test_gym_owner_pays_admin_plan(self):
        res = self.request_for(payer=self.owner, plan=self.admin_plan)
        self.assertEqual(res.status_code, 201)
        uuid = res.json()["data"]["uuid"]
        self.submit(uuid, payer=self.owner)
        self.assertEqual(self.api(self.owner).post(f"/api/payment-requests/{uuid}/verify/").status_code, 404)
        self.assertEqual(self.api(self.admin).post(f"/api/payment-requests/{uuid}/verify/").status_code, 200)
        self.owner.refresh_from_db()
        self.assertIsNotNone(self.owner.membership_end)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(Payment.objects.get().paid_by, self.owner)

    def test_plan_scoping_and_settings(self):
        self.assertEqual(self.request_for(plan=self.admin_plan).status_code, 404)  # member can't use admin plan
        ids = [p["uuid"] for p in self.api(self.member).get("/api/membership-plans/available/").json()["data"]]
        self.assertEqual(ids, [str(self.plan.uuid)])
        res = self.api(self.owner).post("/api/payment-settings/me/", {"payment_upi_id": "bad id"}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.api(self.owner).post("/api/payment-settings/me/", {"payment_upi_id": "ok.name@bank"}, format="json")
        self.assertEqual(res.json()["data"]["payment_upi_id"], "ok.name@bank")
