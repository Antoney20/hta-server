"""
NotificationService — generates guard-style alerts on demand.

Covers:
  - Recent failed login attempts on the user's account
  - Tasks nearing expiry (due within 2 days, not completed)
  - Sub-activities newly assigned to the user (created in last 24 hours)
  - Sub-activities nearing their deadline (due within 2 days, not completed)
"""

from datetime import timedelta

from django.utils import timezone

from app.models import SubActivity
from members.models import Task, TaskStatus



EXPIRY_DAYS          = 2
SUB_ACTIVITY_WINDOW  = timedelta(hours=24)         # "new assignment" look-back window


class NotificationService:

    @classmethod
    def get_alerts(cls, user) -> list[dict]:
        alerts = []
        alerts.extend(cls._login_alerts(user))
        alerts.extend(cls._task_expiry_alerts(user))
        alerts.extend(cls._sub_activity_assigned_alerts(user))
        alerts.extend(cls._sub_activity_deadline_alerts(user))
        return alerts


    @classmethod
    def _login_alerts(cls, user) -> list[dict]:
        if not user.login_attempts:
            return []

        detail = f"{user.login_attempts} failed login attempt{'s' if user.login_attempts != 1 else ''}"
        if user.last_failed_login:
            detail += f" — last at {user.last_failed_login.strftime('%d %b %Y %H:%M')} UTC"
        if user.last_login_ip:
            detail += f" from {user.last_login_ip}"

        return [{
            "type":       "login_failure",
            "severity":   "high" if user.login_attempts >= 3 else "warning",
            "title":      "Suspicious login activity",
            "detail":     detail,
            "timestamp":  user.last_failed_login,
            "action_url": "/portal/settings",
        }]

    @classmethod
    def _task_expiry_alerts(cls, user) -> list[dict]:
        from django.db.models import Q

        today    = timezone.now().date()
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
            alerts.append({
                "type":       "task_expiry",
                "severity":   "high" if days_left == 0 else "warning",
                "title":      f"Task due {label}",
                "detail":     task.title,
                "timestamp":  None,
                "action_url": "/portal/tasks",
                "task_id":    str(task.id),
            })

        return alerts


    @classmethod
    def _sub_activity_assigned_alerts(cls, user) -> list[dict]:
        """
        Sub-activities assigned to this user and created in the last 24 hours.
        Lets the user know something new landed in their queue.
        """
        since = timezone.now() - SUB_ACTIVITY_WINDOW

        subs = (
            SubActivity.objects
            .filter(
                assigned_to=user,
                created_at__gte=since,
            )
            .exclude(status="completed")
            .select_related("activity")
            .only("id", "name", "created_at", "activity__name")
        )

        alerts = []
        for sub in subs:
            alerts.append({
                "type":       "sub_activity_assigned",
                "severity":   "info",
                "title":      "New activity/task assigned ",
                "detail":     f'"{sub.name}" under "{sub.activity.name}"',
                "timestamp":  sub.created_at,
                "action_url": f"/portal/activities/",
                "sub_activity_id": str(sub.id),
            })

        return alerts

    @classmethod
    def _sub_activity_deadline_alerts(cls, user) -> list[dict]:
        """
        Sub-activities assigned to this user with a due_date within the next
        2 days that are not yet completed.

        Requires SubActivity to have a `due_date` DateField.
        If your model uses a different field name, adjust the filter below.
        """
        today    = timezone.now().date()
        deadline = today + timedelta(days=EXPIRY_DAYS)

        subs = (
            SubActivity.objects
            .filter(
                assigned_to=user,
                end_date__range=(today, deadline),
            )
            .exclude(status="completed")
            .select_related("activity")
            .only("id", "name", "end_date", "activity__name")
        )

        alerts = []
        for sub in subs:
            days_left = (sub.end_date - today).days
            label = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
            alerts.append({
                "type":           "sub_activity_deadline",
                "severity":       "high" if days_left == 0 else "warning",
                "title":          f"Activity/task due {label}",
                "detail":         f'"{sub.name}" under "{sub.activity.name}"',
                "timestamp":      None,
                "action_url":     f"/portal/activities/",
                "sub_activity_id": str(sub.id),
            })

        return alerts