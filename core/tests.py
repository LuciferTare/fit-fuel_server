from django.test import TestCase


class HealthCheckTest(TestCase):
    def test_health_check_returns_200(self):
        response = self.client.head("/api/health/")
        self.assertEqual(response.status_code, 200)

    def test_ping_returns_200(self):
        response = self.client.get("/api/ping/")
        self.assertEqual(response.status_code, 200)
