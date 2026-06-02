# import threading

# from django.contrib.auth import get_user_model
# from django.db.models import Q, QuerySet
# from django.utils import timezone
# from rest_framework.exceptions import PermissionDenied, ValidationError

# from members.models import Task, TaskAssignment, TaskStatus
# from members.services.email import send_task_assignment_emails

# User = get_user_model()


# def _is_privileged(user) -> bool:
#     return user.is_staff or user.is_superuser or user.groups.filter(name__in=["admin", "manager"]).exists()


# def _can_act(user, task: Task) -> bool:
#     return task.created_by_id == user.pk or task.assigned_users.filter(pk=user.pk).exists() or _is_privileged(user)


# class TaskService:

#     @classmethod
#     def get_queryset(cls, user, params: dict | None = None) -> QuerySet:
#         params = params or {}

#         qs = Task.objects.all() if _is_privileged(user) else (
#             Task.objects.filter(Q(assigned_users=user) | Q(created_by=user)).distinct()
#         )

#         if s := params.get("status"):
#             qs = qs.filter(status=s)
#         if p := params.get("priority"):
#             qs = qs.filter(priority=p)

#         due = params.get("due")
#         if due:
#             today = timezone.now().date()
#             active = [TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
#             qs = {
#                 "today":    lambda q: q.filter(due_date=today),
#                 "overdue":  lambda q: q.filter(due_date__lt=today, status__in=active),
#                 "upcoming": lambda q: q.filter(due_date__gt=today),
#                 "no_date":  lambda q: q.filter(due_date__isnull=True),
#             }.get(due, lambda q: q)(qs)

#         return qs.select_related("created_by").prefetch_related("assignments__user", "assignments__assigned_by")

#     @classmethod
#     def stats(cls, user) -> dict:
#         qs = cls.get_queryset(user)
#         today = timezone.now().date()
#         active = [TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
#         return {
#             "total": qs.count(),
#             **{s: qs.filter(status=s).count() for s in TaskStatus.values},
#             "overdue": qs.filter(due_date__lt=today, status__in=active).count(),
#             "due_today": qs.filter(due_date=today).count(),
#         }



#     @classmethod
#     def complete_task(cls, user, task: Task) -> Task:
#         if not _can_act(user, task):
#             raise PermissionDenied("You do not have permission to complete this task.")
#         task.status = TaskStatus.COMPLETED
#         task.completed_at = timezone.now()
#         task.save(update_fields=["status", "completed_at", "updated_at"])
#         return task

#     @classmethod
#     def reopen_task(cls, user, task: Task) -> Task:
#         if not _can_act(user, task):
#             raise PermissionDenied("You do not have permission to reopen this task.")
#         task.status = TaskStatus.NEW
#         task.completed_at = None
#         task.save(update_fields=["status", "completed_at", "updated_at"])
#         return task

#     @classmethod
#     def assign_users(cls, requesting_user, task: Task, user_ids: list) -> list[str]:
#         if not _is_privileged(requesting_user):
#             raise PermissionDenied("Only admin or manager can assign tasks.")
#         if not user_ids:
#             raise ValidationError({"user_ids": "Required and must not be empty."})

#         task.assignments.all().delete()
#         assigned = []
#         for uid in user_ids:
#             try:
#                 u = User.objects.get(pk=uid, status="active")
#                 TaskAssignment.objects.create(task=task, user=u, assigned_by=requesting_user)
#                 assigned.append(u.username)
#             except User.DoesNotExist:
#                 continue
#         return assigned

#     @classmethod
#     def update_progress(cls, user, task: Task, progress) -> Task:
#         if not _can_act(user, task):
#             raise PermissionDenied("You do not have permission to update this task.")
#         if progress is None or not (0 <= int(progress) <= 100):
#             raise ValidationError({"progress": "Must be between 0 and 100."})

#         task.progress = progress
#         fields = ["progress", "updated_at"]
#         if int(progress) == 100:
#             task.status = TaskStatus.COMPLETED
#             task.completed_at = timezone.now()
#             fields += ["status", "completed_at"]
#         task.save(update_fields=fields)
#         return task
    
    
#     @classmethod
#     def assign_users(cls, requesting_user, task: Task, user_ids: list) -> list[str]:
#         if not _is_privileged(requesting_user):
#             raise PermissionDenied("Only admin or manager can assign tasks.")
#         if not user_ids:
#             raise ValidationError({"user_ids": "Required and must not be empty."})

#         task.assignments.all().delete()
#         assigned = []
#         assigned_user_objs = []
#         for uid in user_ids:
#             try:
#                 u = User.objects.get(pk=uid, status="active")
#                 TaskAssignment.objects.create(task=task, user=u, assigned_by=requesting_user)
#                 assigned.append(u.username)
#                 assigned_user_objs.append(u)
#             except User.DoesNotExist:
#                 continue

#         if task.send_email_alert and assigned_user_objs:
#             threading.Thread(
#                 target=send_task_assignment_emails,
#                 args=(task, assigned_user_objs),
#                 daemon=True,
#             ).start()

#         return assigned


import threading

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from members.models import Task, TaskAssignment, TaskStatus
from members.services.email import send_task_assignment_emails

User = get_user_model()


def _is_privileged(user) -> bool:
    return user.is_staff or user.is_superuser or user.groups.filter(name__in=["admin", "manager"]).exists()


def _can_act(user, task: Task) -> bool:
    return task.created_by_id == user.pk or task.assigned_users.filter(pk=user.pk).exists() or _is_privileged(user)


class TaskService:

    @classmethod
    def get_queryset(cls, user, params: dict | None = None) -> QuerySet:
        params = params or {}

        qs = Task.objects.all() if _is_privileged(user) else (
            Task.objects.filter(Q(assigned_users=user) | Q(created_by=user)).distinct()
        )

        if s := params.get("status"):
            qs = qs.filter(status=s)
        if p := params.get("priority"):
            qs = qs.filter(priority=p)

        due = params.get("due")
        if due:
            today = timezone.now().date()
            active = [TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
            qs = {
                "today":    lambda q: q.filter(due_date=today),
                "overdue":  lambda q: q.filter(due_date__lt=today, status__in=active),
                "upcoming": lambda q: q.filter(due_date__gt=today),
                "no_date":  lambda q: q.filter(due_date__isnull=True),
            }.get(due, lambda q: q)(qs)

        return qs.select_related("created_by").prefetch_related("assignments__user", "assignments__assigned_by")

    @classmethod
    def stats(cls, user) -> dict:
        qs = cls.get_queryset(user)
        today = timezone.now().date()
        active = [TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
        return {
            "total": qs.count(),
            **{s: qs.filter(status=s).count() for s in TaskStatus.values},
            "overdue": qs.filter(due_date__lt=today, status__in=active).count(),
            "due_today": qs.filter(due_date=today).count(),
        }

    @classmethod
    def complete_task(cls, user, task: Task) -> Task:
        if not _can_act(user, task):
            raise PermissionDenied("You do not have permission to complete this task.")
        task.status = TaskStatus.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        return task

    @classmethod
    def reopen_task(cls, user, task: Task) -> Task:
        if not _can_act(user, task):
            raise PermissionDenied("You do not have permission to reopen this task.")
        task.status = TaskStatus.NEW
        task.completed_at = None
        task.save(update_fields=["status", "completed_at", "updated_at"])
        return task

    @classmethod
    def assign_users(cls, requesting_user, task: Task, user_ids: list) -> list[str]:
        if not _is_privileged(requesting_user):
            raise PermissionDenied("Only admin or manager can assign tasks.")
        if not user_ids:
            raise ValidationError({"user_ids": "Required and must not be empty."})

        task.assignments.all().delete()
        assigned = []
        assigned_user_objs = []
        for uid in user_ids:
            try:
                u = User.objects.get(pk=uid, status="active")
                TaskAssignment.objects.create(task=task, user=u, assigned_by=requesting_user)
                assigned.append(u.username)
                assigned_user_objs.append(u)
            except User.DoesNotExist:
                continue

        if task.send_email_alert and assigned_user_objs:
            threading.Thread(
                target=send_task_assignment_emails,
                args=(task, assigned_user_objs),
                daemon=True,
            ).start()

        return assigned

    @classmethod
    def update_progress(cls, user, task: Task, progress) -> Task:
        if not _can_act(user, task):
            raise PermissionDenied("You do not have permission to update this task.")
        if progress is None or not (0 <= int(progress) <= 100):
            raise ValidationError({"progress": "Must be between 0 and 100."})

        task.progress = progress
        fields = ["progress", "updated_at"]
        if int(progress) == 100:
            task.status = TaskStatus.COMPLETED
            task.completed_at = timezone.now()
            fields += ["status", "completed_at"]
        task.save(update_fields=fields)
        return task

    # ---------- helpers for serializer/viewset ----------
    @classmethod
    def sync_assignments(cls, task: Task, user_ids: list, requesting_user) -> list:
        """
        Reconcile task.assignments to match user_ids.
        Returns list of newly added User objects.
        Empty/None user_ids clears all assignments.
        """
        if not user_ids:
            task.assignments.all().delete()
            return []

        requested = set(user_ids)
        existing  = set(task.assignments.values_list('user_id', flat=True))

        task.assignments.exclude(user_id__in=requested).delete()

        newly_assigned = []
        for uid in requested - existing:
            try:
                u = User.objects.get(pk=uid, status="active")
                TaskAssignment.objects.create(task=task, user=u, assigned_by=requesting_user)
                newly_assigned.append(u)
            except User.DoesNotExist:
                continue

        if task.send_email_alert and newly_assigned:
            threading.Thread(
                target=send_task_assignment_emails,
                args=(task, newly_assigned),
                daemon=True,
            ).start()

        return newly_assigned

    @classmethod
    def sync_completion(cls, task: Task) -> None:
        """Keep completed_at in sync with status."""
        if task.status == TaskStatus.COMPLETED and not task.completed_at:
            task.completed_at = timezone.now()
            task.save(update_fields=["completed_at"])
        elif task.status != TaskStatus.COMPLETED and task.completed_at:
            task.completed_at = None
            task.save(update_fields=["completed_at"])