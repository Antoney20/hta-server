
from datetime import date, timedelta


from django.contrib.auth import get_user_model
from django.db.models import Count, F, Q
from django.utils import timezone

from app.models import (
    CriteriaAppraisalScore,
    InterventionScore,
    InterventionStatusUpdate,
    InterventionSystemCategory,
    FeedbackEmailLog,
    SystemCategory,
)
from members.models import Task, TaskStatus
from users.models import InterventionProposal, UserRole

User = get_user_model()


def _has_role(user, *roles) -> bool:
    return user.is_authenticated and any(user.has_role(r) for r in roles)


def _is_admin(user) -> bool:
    return _has_role(user, UserRole.ADMIN) or user.is_staff or user.is_superuser


def _is_secretariat(user) -> bool:
    return _has_role(user, UserRole.SECRETARIAT)


def _is_swg(user) -> bool:
    return _has_role(user, UserRole.SWG)


def _is_panel(user) -> bool:
    return _has_role(user, UserRole.PANEL)


def _is_admin_or_secretariat(user) -> bool:
    return _is_admin(user) or _is_secretariat(user)


def _is_decision_viewer(user) -> bool:
    """admin, secretariat, swg, panel can see decisions."""
    return _is_admin(user) or _is_secretariat(user) or _is_swg(user) or _is_panel(user)


start_date = date(2025, 11, 4)
# ---------------------------------------------------------------------------
# 1. Users
#    admin  → full breakdown by role + active count
#    others → own profile summary only
# ---------------------------------------------------------------------------

def _user_stats(user) -> dict:
    if _is_admin(user):
        active_qs = User.objects.filter(is_active=True)
        return {
            "scope": "all",
            "total_active": active_qs.count(),
            "by_role": list(
                active_qs.values("role")
                .annotate(count=Count("id"))
                .order_by("-count")
            ),
        }

    # Non-admin: return just their own summary
    return {
        "scope": "self",
        "username": user.username,
        "email": user.email,
        "role": getattr(user, "role", None),
        "is_active": user.is_active,
        "avatar": str(user.profile_image) if user.profile_image else None,
    }


# ---------------------------------------------------------------------------
# 2. Tasks
#    admin / secretariat → all tasks
#    others              → assigned to OR created by the user
# ---------------------------------------------------------------------------

def _task_stats(user) -> dict:
    today = timezone.now().date()
    active_statuses = [TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]

    if _is_admin_or_secretariat(user):
        base = Task.objects.all()
    else:
        base = Task.objects.filter(
            Q(assigned_users=user) | Q(created_by=user)
        ).distinct()

    by_status = {
        r["status"]: r["count"]
        for r in base.values("status").annotate(count=Count("id"))
    }

    total = base.count()
    completed = base.filter(status=TaskStatus.COMPLETED).count()

    return {
        "total": total,
        "completed": completed,
        "not_completed": total - completed,
        "overdue": base.filter(due_date__lt=today, status__in=active_statuses).count(),
        "upcoming_7d": base.filter(
            due_date__range=(today, today + timedelta(days=7)),
            status__in=active_statuses,
        ).count(),
        "by_status": by_status,
    }


# ---------------------------------------------------------------------------
# 3. Interventions / Proposals
#    Visible to all authenticated users.
#    Grouped by day from earliest record to today.
# ---------------------------------------------------------------------------


def _proposal_stats() -> dict:
    base = InterventionProposal.objects.all()
    today = timezone.now().date()

    start_date = date(2025, 11, 4)

    # Daily counts
    daily_counts_qs = (
        base.filter(submitted_at__date__gte=start_date)
        .extra(select={"day": "DATE(submitted_at)"})
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    daily_map = {row["day"]: row["count"] for row in daily_counts_qs}

    daily_trend = []
    cursor = start_date
    while cursor <= today:
        daily_trend.append({
            "date": cursor.isoformat(),
            "count": daily_map.get(cursor, 0)
        })
        cursor += timedelta(days=1)

    # Monthly trend (last 6 months)
    now = timezone.now()
    monthly_trend = []
    for i in range(5, -1, -1):
        m_start = (now - timedelta(days=30 * i)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        m_end = (m_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

        monthly_trend.append({
            "month": m_start.strftime("%b %Y"),
            "count": base.filter(submitted_at__range=(m_start, m_end)).count(),
        })

    return {
        "total": base.count(),
        "daily_trend": daily_trend,
        "monthly_trend": monthly_trend,
    }

# ---------------------------------------------------------------------------
# 4. Topic Prioritization (System Categories)
#    Visible to all authenticated users.
# ---------------------------------------------------------------------------

def _topic_prioritization_stats() -> dict:
    total_categories = SystemCategory.objects.count()

    # Interventions grouped by system category
    by_category = list(
        SystemCategory.objects.annotate(
            intervention_count=Count("interventions__intervention", distinct=True)
        )
        .values("name", "intervention_count")
        .order_by("-intervention_count")
    )

    # Interventions that have NO system category assigned
    categorised_ids = (
        InterventionSystemCategory.objects.values_list("intervention_id", flat=True)
        .distinct()
    )
    uncategorised_count = (
        InterventionProposal.objects.exclude(id__in=categorised_ids).count()
    )

    return {
        "total_system_categories": total_categories,
        "by_system_category": by_category,
        "uncategorised_interventions": uncategorised_count,
    }


# ---------------------------------------------------------------------------
# 5. Scoring Progress
#    admin / secretariat / swg only.
#    Progress bar = scored_count / total_interventions.
# ---------------------------------------------------------------------------

def _scoring_stats(user) -> dict | None:
    if not (_is_admin(user) or _is_secretariat(user) or _is_swg(user)):
        return None

    total_interventions = InterventionProposal.objects.count()

    if _is_admin(user) or _is_secretariat(user):
        scored_count = (
            InterventionScore.objects.values("intervention").distinct().count()
        )
        by_reviewer = list(
            InterventionScore.objects
            .values(reviewer_username=F("reviewer__username"))
            .annotate(scored_count=Count("intervention", distinct=True))
            .order_by("-scored_count")[:10]
        )
    else:
        # SWG: own scoring only
        scored_count = (
            InterventionScore.objects.filter(reviewer=user)
            .values("intervention")
            .distinct()
            .count()
        )
        by_reviewer = []

    return {
        "total_interventions": total_interventions,
        "scored_interventions": scored_count,
        "unscored_interventions": max(total_interventions - scored_count, 0),
        "progress_pct": round(scored_count / total_interventions * 100, 1) if total_interventions else 0,
        "by_reviewer": by_reviewer,
    }


# ---------------------------------------------------------------------------
# 6. Decisions & Panel Movement
#    admin, secretariat, swg, panel.
# ---------------------------------------------------------------------------

def _decision_stats(user) -> dict | None:
    if not _is_decision_viewer(user):
        return None

    qs = InterventionStatusUpdate.objects.all()
    total = qs.count()
    moved_to_panel = qs.filter(move_to_panel=True).count()

    by_decision = list(
        qs.filter(decision__isnull=False)
        .values(decision_name=F("decision__name"))
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return {
        "total_status_updates": total,
        "moved_to_panel": moved_to_panel,
        "by_decision": by_decision,
    }


# ---------------------------------------------------------------------------
# 7. Panel Info
#    panel, secretariat, admin.
# ---------------------------------------------------------------------------

def _panel_stats(user) -> dict | None:
    if not (_is_admin(user) or _is_secretariat(user) or _is_panel(user)):
        return None

    total_scored = (
        CriteriaAppraisalScore.objects.values("intervention").distinct().count()
    )
    in_panel_count = (
        InterventionStatusUpdate.objects.filter(move_to_panel=True)
        .values("intervention")
        .distinct()
        .count()
    )

    panel_members = list(
        User.objects.filter(role=UserRole.PANEL, is_active=True)
        .values("username", "email")
        .order_by("username")
    )
    # Attach avatar URL if available
    for member in panel_members:
        u = User.objects.filter(username=member["username"]).only("profile_image").first()
        member["avatar"] = str(u.profile_image) if u and u.profile_image else None
        
    return {
        "total_scored_interventions": total_scored,
        "in_panel_count": in_panel_count,
        "panel_members": panel_members,
        "note": "More panel features coming soon.",
    }


# ---------------------------------------------------------------------------
# 8. Feedback Email Logs
#    admin only.
# ---------------------------------------------------------------------------

def _feedback_stats() -> dict:
    logs = FeedbackEmailLog.objects.all()
    sent = logs.filter(status="sent")
    failed = logs.filter(status="failed")

    recent_failed = list(
        failed.select_related("category", "intervention")
        .order_by("-last_attempt")[:20]
        .values(
            "id",
            "recipient",
            "error_message",
            "retry_count",
            "last_attempt",
            category_name=F("category__name"),
        )
    )

    by_category = list(
        logs.values(category_name=F("category__name"))
        .annotate(
            total=Count("id"),
            sent_count=Count("id", filter=Q(status="sent")),
            failed_count=Count("id", filter=Q(status="failed")),
        )
        .order_by("-total")
    )

    return {
        "total_sent": sent.count(),
        "total_failed": failed.count(),
        "by_category": by_category,
        "recent_failed": recent_failed,
    }


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class DashboardService:
    """
    Call `DashboardService.get_stats(request.user)` in your view.
    Returns only the sections the user's role is permitted to see.
    None-valued sections are stripped before returning.
    """

    @classmethod
    def get_stats(cls, user) -> dict:
        data: dict = {
            # visible to all
            "users": _user_stats(user),
            "tasks": _task_stats(user),
            "proposals": _proposal_stats(),
            "topic_prioritization": _topic_prioritization_stats(),

            # role-gated (None means no access)
            "scoring": _scoring_stats(user),
            "decisions": _decision_stats(user),
            "panel": _panel_stats(user),
        }

        # admin-only section
        if _is_admin(user):
            data["feedback"] = _feedback_stats()

        # Strip sections the role cannot see
        return {k: v for k, v in data.items() if v is not None}
    
    
    
"""
DashboardService — role-aware stats for the dashboard GET endpoint.

Role visibility matrix
──────────────────────────────────────────────────────────────────
Section                     admin  secretariat  swg   panel  others
─────────────────────────── ─────  ───────────  ───   ─────  ──────
users (all / own summary)     ✓         –        –      –      –
tasks                         ✓         ✓        ✓      ✓      ✓   (own only for non-admin)
proposals / interventions     ✓         ✓        ✓      ✓      ✓
topic prioritization          ✓         ✓        ✓      ✓      ✓
scoring progress              ✓         ✓        ✓      –      –
decisions / panel movement    ✓         ✓        ✓      ✓      –
panel info                    ✓         ✓        –      ✓      –
feedback email logs           ✓         –        –      –      –
──────────────────────────────────────────────────────────────────
"""