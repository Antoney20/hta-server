"""
NotificationService — generates guard-style alerts on demand.

Covers:
  - Recent failed login attempts on the user's account
  - Tasks nearing expiry (due within 2 days, not completed)

"""

from datetime import timedelta

from django.utils import timezone

from members.models import Task, TaskStatus



EXPIRY_DAYS = 2  


class NotificationService:

    @classmethod
    def get_alerts(cls, user) -> list[dict]:
        alerts = []
        alerts.extend(cls._login_alerts(user))
        alerts.extend(cls._task_expiry_alerts(user))
        # Most recent first — login alerts have no date so they sort to top
        return alerts

    # ------------------------------------------------------------------
    # Login guard
    # ------------------------------------------------------------------

    @classmethod
    def _login_alerts(cls, user) -> list[dict]:
        if not user.login_attempts or user.login_attempts == 0:
            return []

        detail = f"{user.login_attempts} failed login attempt{'s' if user.login_attempts != 1 else ''}"
        if user.last_failed_login:
            detail += f" — last at {user.last_failed_login.strftime('%d %b %Y %H:%M')} UTC"
        if user.last_login_ip:
            detail += f" from {user.last_login_ip}"

        return [
            {
                "type": "login_failure",
                "severity": "high" if user.login_attempts >= 3 else "warning",
                "title": "Suspicious login activity",
                "detail": detail,
                "timestamp": user.last_failed_login,
                "action_url": "/portal/settings",
            }
        ]

    # ------------------------------------------------------------------
    # Task expiry guard
    # ------------------------------------------------------------------

    @classmethod
    def _task_expiry_alerts(cls, user) -> list[dict]:
        from django.db.models import Q

        today = timezone.now().date()
        deadline = today + timedelta(days=EXPIRY_DAYS)

        tasks = (
            Task.objects.filter(
                Q(assigned_users=user) | Q(created_by=user),
                due_date__range=(today, deadline),
                status__in=[TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW],
            )
            .distinct()
            .only("id", "title", "due_date", "status")
        )

        alerts = []
        for task in tasks:
            days_left = (task.due_date - today).days
            label = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
            alerts.append(
                {
                    "type": "task_expiry",
                    "severity": "high" if days_left == 0 else "warning",
                    "title": f'Task due {label}',
                    "detail": task.title,
                    "timestamp": None,
                    "action_url": f"/portal/tasks",
                    "task_id": str(task.id),
                }
            )

        return alerts