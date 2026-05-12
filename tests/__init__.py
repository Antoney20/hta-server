"""
tests/__init__.py

Test suite for BPTAP  Server.

Structure:
    test_settings.py   — security & config sanity checks
    test_urls.py       — URL routing & namespace smoke tests
    test_auth.py       — JWT register / login / refresh / RBAC
    test_security.py   — throttling, CORS, headers, injection probes

Run all:
    python manage.py test tests

Run a single module:
    python manage.py test tests.test_auth

Run a single test:
    python manage.py test tests.test_auth.LoginTest.test_login_with_valid_credentials_returns_200_with_tokens

With verbosity:
    python manage.py test tests -v 2

Coverage report (requires coverage):
    coverage run manage.py test tests
    coverage report -m
    coverage html  # opens htmlcov/index.html
"""