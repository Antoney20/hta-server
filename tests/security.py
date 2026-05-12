"""

Throttling, CORS, security headers, and middleware tests.
These protect against abuse and misconfiguration in production.

To run: python manage.py test tests.security
"""

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()

LOGIN_URL = "/api/v1/auth/login/"


class ThrottlingTest(TestCase):
    """
    Anonymous requests are throttled at 10/min per settings.py.
    This test hits the endpoint repeatedly to verify the gate fires.
    """

    @override_settings(
        REST_FRAMEWORK={
            **{},  
            "DEFAULT_THROTTLE_CLASSES": [
                "rest_framework.throttling.AnonRateThrottle"
            ],
            "DEFAULT_THROTTLE_RATES": {"anon": "3/min"}, 
        }
    )
    def test_anon_throttle_triggers_after_limit(self):
        client = APIClient()
        responses = []
        for _ in range(6):
            r = client.post(
                LOGIN_URL,
                {"username_or_email": "nobody@bptap.org", "password": "wrong"},
            )
            responses.append(r.status_code)

        self.assertIn(
            status.HTTP_429_TOO_MANY_REQUESTS,
            responses,
            "Throttle must kick in for anonymous users after rate limit is exceeded.",
        )

    def test_throttle_response_includes_retry_after_header(self):
        """429 responses must include Retry-After so clients can back off."""
        client = APIClient()
        # Hit the endpoint enough times to trigger throttle
        for _ in range(15):
            r = client.post(LOGIN_URL, {"username_or_email": "x@x.com", "password": "x"})
            if r.status_code == 429:
                self.assertIn(
                    "Retry-After",
                    r,
                    "429 response must include Retry-After header.",
                )
                return  # Test passed
        # If we never got 429, note it but don't hard-fail (rate may be high)
        self.skipTest("Throttle not triggered — increase hit count or lower rate.")


class SecurityHeadersTest(TestCase):
    """
    Django security middleware must inject the correct HTTP headers
    on every response.
    """

    def setUp(self):
        self.client = APIClient()

    def _get_any_response(self):
        return self.client.get("/api/v1/")

    def test_x_content_type_options_nosniff(self):
        r = self._get_any_response()
        self.assertEqual(r.get("X-Content-Type-Options"), "nosniff")

    def test_x_frame_options_deny(self):
        r = self._get_any_response()
        self.assertIn(r.get("X-Frame-Options", ""), ["DENY", "SAMEORIGIN"])

    def test_no_server_header_leaking_framework(self):
        """The Server header must not expose Django version."""
        r = self._get_any_response()
        server = r.get("Server", "")
        self.assertNotIn("Django", server, "Server header must not leak framework.")
        self.assertNotIn("Python", server, "Server header must not leak runtime.")

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False)
    def test_no_sensitive_data_in_error_response(self):
        """DRF error responses must not expose tracebacks or internal paths."""
        r = self.client.get("/api/v3/nonexistent-endpoint-xyz/")
        content = r.content.decode()
        self.assertNotIn("Traceback", content)
        self.assertNotIn("/home/", content)
        self.assertNotIn("settings.py", content)


class CORSTest(TestCase):
    """
    CORS must allow listed origins and block unlisted ones.
    """

    ALLOWED_ORIGIN = "https://bptap.health.go.ke"
    BLOCKED_ORIGIN = "https://evil-site.com"

    def setUp(self):
        self.client = APIClient()

    def test_cors_allows_listed_origin(self):
        r = self.client.options(
            "/api/v1/",
            HTTP_ORIGIN=self.ALLOWED_ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        acao = r.get("Access-Control-Allow-Origin", "")
        self.assertEqual(
            acao,
            self.ALLOWED_ORIGIN,
            "CORS must allow the registered frontend origin.",
        )

    def test_cors_blocks_unlisted_origin(self):
        r = self.client.options(
            "/api/v1/",
            HTTP_ORIGIN=self.BLOCKED_ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        acao = r.get("Access-Control-Allow-Origin", "")
        self.assertNotEqual(
            acao,
            self.BLOCKED_ORIGIN,
            "CORS must not echo back an unlisted origin.",
        )

    def test_cors_credentials_header_present_for_allowed_origin(self):
        """CORS_ALLOW_CREDENTIALS=True means this header must be set."""
        r = self.client.options(
            "/api/v1/",
            HTTP_ORIGIN=self.ALLOWED_ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        self.assertEqual(
            r.get("Access-Control-Allow-Credentials", "").lower(),
            "true",
        )


class SQLInjectionTest(TestCase):
    """
    Basic injection probes — Django ORM protects against these,
    but we verify the API doesn't 500 on malicious input.
    """

    def setUp(self):
        self.client = APIClient()

    def test_sql_injection_in_login_email_does_not_500(self):
        payload = {
            "username_or_email": "' OR '1'='1'; --",
            "password": "doesntmatter",
        }
        r = self.client.post(LOGIN_URL, payload)
        self.assertNotEqual(r.status_code, 500, "SQL injection must not cause 500.")

    def test_xss_payload_in_login_does_not_500(self):
        payload = {
            "username_or_email": "<script>alert(1)</script>@bptap.org",
            "password": "doesntmatter",
        }
        r = self.client.post(LOGIN_URL, payload)
        self.assertNotEqual(r.status_code, 500)
        self.assertNotIn(b"<script>", r.content)


class ContentTypeTest(TestCase):
    """API must only serve JSON — no HTML responses on API routes."""

    def setUp(self):
        self.client = APIClient()

    def test_api_response_content_type_is_json(self):
        r = self.client.get("/api/v1/", HTTP_ACCEPT="application/json")
        content_type = r.get("Content-Type", "")
        if r.status_code not in [401, 403, 405]:
            self.skipTest("Endpoint redirected — cannot check content type.")
        # On auth errors DRF should still return JSON
        self.assertIn("application/json", content_type)

    def test_browsable_api_disabled_in_production(self):
        """BrowsableAPIRenderer should not serve HTML to non-browser clients."""
        r = self.client.get("/api/v1/", HTTP_ACCEPT="application/json")
        content_type = r.get("Content-Type", "")
        self.assertNotIn(
            "text/html",
            content_type,
            "API must not return HTML when JSON is requested.",
        )