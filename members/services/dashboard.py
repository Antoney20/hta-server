from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.utils import timezone

from app.models import InterventionPackage, NationalProgram, NationalProgramProposal, SubActivity
from members.models import Task
from users.models import InterventionProposal, UserRole

User = get_user_model()


def _has_role(user, *roles) -> bool:
    return user.is_authenticated and any(user.has_role(r) for r in roles)


def _is_admin(user) -> bool:
    return _has_role(user, UserRole.ADMIN) or user.is_staff or user.is_superuser



def _top_counts(user) -> dict:
    """
    Scalar cards shown to everyone.
      - intervention proposals / national programs / national program proposals:
        global totals (same for all users)
      - my_tasks / my_activities: admin → all, others → their own
    """
    admin = _is_admin(user)

    # Tasks owned by the user = assigned to them OR created by them
    if admin:
        task_qs = Task.objects.all()
    else:
        task_qs = Task.objects.filter(
            Q(assigned_users=user) | Q(created_by=user)
        ).distinct()

    # SubActivities owned by the user = assigned to them (admin → all)
    if admin:
        activity_qs = SubActivity.objects.all()
    else:
        activity_qs = SubActivity.objects.filter(assigned_to=user).distinct()

    return {
        "total_intervention_proposals": InterventionProposal.objects.count(),
        "total_national_programs": NationalProgram.objects.count(),
        "total_national_program_proposals": NationalProgramProposal.objects.count(),
        "my_tasks": task_qs.count(),
        "my_activities": activity_qs.count(),
        "scope": "all" if admin else "self",
    }


def _fill_series(rows, key, start, step_days, buckets, label_fmt):
    """
    rows      : queryset .values(period=Trunc..., count=...)
    key       : "period" key in each row
    start     : first bucket date (date)
    step_days : bucket width in days (1 / 7 / ~30 handled by caller for months)
    buckets   : ordered list of bucket start-dates to emit
    label_fmt : callable(date) -> label string
    Returns a gap-filled list of { "label", "date", "count" }.
    """
    found = {}
    for r in rows:
        d = r[key]
        if hasattr(d, "date"):
            d = d.date()
        found[d] = r["count"]
    return [
        {"label": label_fmt(b), "date": b.isoformat(), "count": found.get(b, 0)}
        for b in buckets
    ]


def _submission_trends() -> dict:
    """
    InterventionProposal submissions bucketed three ways, each over a bounded,
    gap-filled window so empty buckets show 0.
      daily   : last 30 days
      weekly  : last 12 ISO weeks (weeks start Monday)
      monthly : last 12 months
    """
    today = timezone.localdate()
    base = InterventionProposal.objects.all()

    # ── Daily: last 30 days ──
    day_start = today - timedelta(days=29)
    day_rows = (
        base.filter(submitted_at__date__gte=day_start)
        .annotate(period=TruncDay("submitted_at"))
        .values("period")
        .annotate(count=Count("id"))
    )
    day_buckets = [day_start + timedelta(days=i) for i in range(30)]
    daily = _fill_series(
        day_rows, "period", day_start, 1, day_buckets,
        lambda d: d.strftime("%d %b"),
    )

    # ── Weekly: last 12 weeks (align to Monday) ──
    this_monday = today - timedelta(days=today.weekday())
    week_start = this_monday - timedelta(weeks=11)
    week_rows = (
        base.filter(submitted_at__date__gte=week_start)
        .annotate(period=TruncWeek("submitted_at"))
        .values("period")
        .annotate(count=Count("id"))
    )
    week_buckets = [week_start + timedelta(weeks=i) for i in range(12)]
    weekly = _fill_series(
        week_rows, "period", week_start, 7, week_buckets,
        lambda d: f"{d.strftime('%d %b')}",
    )

    # ── Monthly: last 12 months ──
    first_of_this_month = today.replace(day=1)
    month_buckets = []
    cursor = first_of_this_month
    for _ in range(12):
        month_buckets.append(cursor)
        # step back one month
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_buckets.reverse()
    month_start = month_buckets[0]

    month_rows = (
        base.filter(submitted_at__date__gte=month_start)
        .annotate(period=TruncMonth("submitted_at"))
        .values("period")
        .annotate(count=Count("id"))
    )
    monthly = _fill_series(
        month_rows, "period", month_start, 30, month_buckets,
        lambda d: d.strftime("%b %Y"),
    )

    return {"daily": daily, "weekly": weekly, "monthly": monthly}


# ── 3. Packages → intervention counts (all users) ─────────────────────────────

def _package_stats() -> dict:
    """
    Each package with its InterventionProposal count. All packages included
    (zeros shown), ordered by count desc. Plus unassigned interventions.
    """
    by_package = list(
        InterventionPackage.objects
        .annotate(intervention_count=Count("interventions", distinct=True))
        .values("id", "name", "intervention_count")
        .order_by("-intervention_count", "name")
    )
    # normalise UUID/int id to str for the client
    for row in by_package:
        row["id"] = str(row["id"])

    unassigned = InterventionProposal.objects.filter(package__isnull=True).count()

    return {
        "total_packages": len(by_package),
        "by_package": by_package,
        "unassigned_interventions": unassigned,
    }



class DashboardService:
    """
    DashboardService.get_stats(request.user)

    Returns three sections, all visible to every authenticated user:
      counts   — top-line scalar cards (my_tasks / my_activities are per-user)
      trends   — InterventionProposal submissions by day / week / month
      packages — intervention count per package (replaces system categorisation)
    """

    @classmethod
    def get_stats(cls, user) -> dict:
        return {
            "counts": _top_counts(user),
            "trends": _submission_trends(),
            "packages": _package_stats(),
        }