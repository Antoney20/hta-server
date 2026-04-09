"""
DashboardService — unified stats for the dashboard GET endpoint.

Sections:
  - Task stats        (total, upcoming, overdue, by status)
  - Proposal stats    (total, by month, by system category)
  - Scoring stats     (role-aware: own scores / all scores)
  - Decision stats    (InterventionStatusUpdate grouped by decision)
  - System categories (InterventionSystemCategory counts)
  - User breakdown    (admin only — users grouped by role)
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from django.utils import timezone

from app.models import InterventionScore, InterventionStatusUpdate, InterventionSystemCategory, SystemCategory
from members.models import Task, TaskStatus
from users.models import InterventionProposal



User = get_user_model()


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def _is_admin(user) -> bool:
    return user.is_staff or user.is_superuser or getattr(user, "role", None) == "admin"


def _is_secretariat(user) -> bool:
    return getattr(user, "role", None) == "secretariat"


def _is_swg(user) -> bool:
    return getattr(user, "role", None) == "swg"


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def _task_stats(user) -> dict:
    today = timezone.now().date()
    active = [TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]

    if _is_admin(user) or _is_secretariat(user):
        base = Task.objects.all()
    else:
        base = Task.objects.filter(
            Q(assigned_users=user) | Q(created_by=user)
        ).distinct()

    by_status = {
        r["status"]: r["count"]
        for r in base.values("status").annotate(count=Count("id"))
    }

    return {
        "total": base.count(),
        "completed": base.filter(status=TaskStatus.COMPLETED).count(),
        "overdue": base.filter(due_date__lt=today, status__in=active).count(),
        "upcoming": base.filter(
            due_date__range=(today, today + timedelta(days=7)),
            status__in=active,
        ).count(),
        "by_status": by_status,
    }


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

def _proposal_stats() -> dict:
    base = InterventionProposal.objects.all()
    now = timezone.now()

    monthly = []
    for i in range(5, -1, -1):
        start = (now - timedelta(days=30 * i)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
        monthly.append({
            "month": start.strftime("%b %Y"),
            "count": base.filter(submitted_at__range=(start, end)).count(),
        })

    by_category = list(
        InterventionSystemCategory.objects.values(name=F("system_category__name"))
        .annotate(count=Count("intervention", distinct=True))
        .order_by("-count")
    )

    return {
        "total": base.count(),
        "monthly_trend": monthly,
        "by_system_category": by_category,
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _scoring_stats(user) -> dict:
    """
    admin   — all scored interventions + breakdown by reviewer
    swg                  — only this reviewer's scored interventions
    others                — 0
    """
    if _is_admin(user):
        return {
            "total_scored_interventions": (
                InterventionScore.objects.values("intervention").distinct().count()
            ),
            "by_reviewer": list(
                InterventionScore.objects.values(reviewer_username=F("reviewer__username"))
                .annotate(count=Count("intervention", distinct=True))
                .order_by("-count")[:10]
            ),
        }

    if _is_swg(user):
        return {
            "total_scored_interventions": (
                InterventionScore.objects.filter(reviewer=user)
                .values("intervention")
                .distinct()
                .count()
            ),
            "by_reviewer": [],
        }

    return {"total_scored_interventions": 0, "by_reviewer": []}


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def _decision_stats() -> dict:
    return {
        "total_updates": InterventionStatusUpdate.objects.count(),
        "by_decision": list(
            InterventionStatusUpdate.objects.filter(decision__isnull=False)
            .values(decision_name=F("decision__name"))
            .annotate(count=Count("id"))
            .order_by("-count")
        ),
    }


# ---------------------------------------------------------------------------
# System categories
# ---------------------------------------------------------------------------

def _system_category_stats() -> list[dict]:
    return list(
        SystemCategory.objects.annotate(
            intervention_count=Count("interventions__intervention", distinct=True)
        )
        .values("name", "intervention_count")
        .order_by("-intervention_count")
    )


# ---------------------------------------------------------------------------
# Users (admin only)
# ---------------------------------------------------------------------------

def _user_stats() -> dict:
    active = User.objects.filter(is_active=True)
    return {
        "total_active": active.count(),
        "by_role": list(
            active.values("role").annotate(count=Count("id")).order_by("-count")
        ),
    }


class DashboardService:

    @classmethod
    def get_stats(cls, user) -> dict:
        data = {
            "tasks": _task_stats(user),
            "proposals": _proposal_stats(),
            "scoring": _scoring_stats(user),
            "decisions": _decision_stats(),
            "system_categories": _system_category_stats(),
        }
        if _is_admin(user):
            data["users"] = _user_stats()
        return data