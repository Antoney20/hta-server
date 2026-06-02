"""
tests/__init__.py

Test suite for BPTAP  Server.

Structure:
    test/settings.py   — security & config sanity checks
    test/urls.py       — URL routing & namespace smoke tests
    test/security.py   — throttling, CORS, headers, injection probes

Run all:
    python manage.py test tests

Run a single module:
    python manage.py test tests.settings

Run a single test:
    python manage.py test tests.security.ThrottlingTest.test_anon_throttle_triggers_after_limit

With verbosity:
    python manage.py test tests -v 2

Coverage report (requires coverage):
    coverage run manage.py test tests
    coverage report -m
    coverage html  # opens htmlcov/index.html
"""