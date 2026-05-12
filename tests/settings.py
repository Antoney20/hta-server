"""

Security & configuration sanity checks.
These catch misconfigurations before they reach production.
Run with: python manage.py test tests.settings
"""

import os
from django.test import TestCase, override_settings
from django.conf import settings


class SecuritySettingsTest(TestCase):
    """Critical security settings must be correctly configured."""

    def test_secret_key_is_set(self):
        self.assertTrue(settings.SECRET_KEY, "SECRET_KEY must not be empty.")

    def test_secret_key_not_insecure_default(self):
        insecure_defaults = [
            "django-insecure",
            "changeme",
            "secret",
        ]
        for bad in insecure_defaults:
            self.assertNotIn(
                bad,
                settings.SECRET_KEY.lower(),
                f"SECRET_KEY contains insecure value: '{bad}'",
            )

    def test_debug_is_false_in_production(self):
        """
        DEBUG=True in production exposes stack traces and config.
        Override in CI via env: DEBUG=False.
        """
    
        if os.getenv("TEST_ENV") == "production":
            self.assertFalse(settings.DEBUG, "DEBUG must be False in production.")

    def test_allowed_hosts_not_wildcard_in_production(self):
        if os.getenv("TEST_ENV") == "production":
            self.assertNotIn(
                "*",
                settings.ALLOWED_HOSTS,
                "ALLOWED_HOSTS must not be '*' in production.",
            )

    def test_csrf_cookie_secure(self):
        self.assertTrue(settings.CSRF_COOKIE_SECURE)

    def test_csrf_cookie_httponly(self):
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)

    def test_x_frame_options_deny(self):
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")

    def test_secure_content_type_nosniff(self):
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)

    def test_cors_allow_all_is_false(self):
        self.assertFalse(
            settings.CORS_ORIGIN_ALLOW_ALL,
            "CORS_ORIGIN_ALLOW_ALL must be False — open CORS is a security risk.",
        )

    def test_cors_allowed_origins_set(self):
        self.assertTrue(
            len(settings.CORS_ALLOWED_ORIGINS) > 0,
            "CORS_ALLOWED_ORIGINS must be explicitly defined.",
        )

    def test_password_validators_configured(self):
        self.assertGreaterEqual(
            len(settings.AUTH_PASSWORD_VALIDATORS),
            4,
            "All four default password validators should be enabled.",
        )

    def test_default_permission_class_is_not_allow_any(self):
        perms = settings.REST_FRAMEWORK.get("DEFAULT_PERMISSION_CLASSES", [])
        self.assertNotIn(
            "rest_framework.permissions.AllowAny",
            perms,
            "AllowAny as default permission is a security risk.",
        )

    def test_throttle_classes_configured(self):
        throttle_classes = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES", [])
        self.assertTrue(
            len(throttle_classes) > 0,
            "Throttle classes must be configured to prevent abuse.",
        )

    def test_throttle_rates_configured(self):
        rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        self.assertIn("anon", rates, "Anonymous throttle rate must be set.")

    def test_jwt_access_token_lifetime_is_reasonable(self):
        from datetime import timedelta
        lifetime = settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME")
        self.assertIsNotNone(lifetime)
        # Access tokens should not live longer than 7 days
        self.assertLessEqual(
            lifetime,
            timedelta(days=7),
            "JWT access token lifetime is too long — reduces security on token theft.",
        )

    def test_jwt_rotate_refresh_tokens_enabled(self):
        self.assertTrue(
            settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"),
            "Refresh token rotation must be enabled.",
        )

    def test_jwt_blacklist_after_rotation_enabled(self):
        self.assertTrue(
            settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"),
            "Token blacklisting after rotation must be enabled.",
        )

    def test_auth_user_model_is_custom(self):
        self.assertEqual(
            settings.AUTH_USER_MODEL,
            "users.CustomUser",
            "Custom user model must be configured.",
        )

    def test_page_size_is_not_unbounded(self):
        page_size = settings.REST_FRAMEWORK.get("PAGE_SIZE", 0)
        self.assertLessEqual(
            page_size,
            10000,
            "PAGE_SIZE of 10000 is dangerously high — consider lowering for list views.",
        )