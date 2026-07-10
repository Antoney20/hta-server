from datetime import timedelta
from django.utils import timezone
from app.models import AppraisalRun


RUN_STALE_AFTER = timedelta(minutes=5)


def generation_status() -> dict:
    """
    Is a generation in progress right now? Derived from AppraisalRun state. A run counts as 'in progress' if it was created within the stale
    window and has neither completed (parsed_ok) nor failed (error) yet.
    """
    cutoff = timezone.now() - RUN_STALE_AFTER
    active = (
        AppraisalRun.objects
        .filter(created_at__gte=cutoff, parsed_ok=False, error__in=["", None])
        .order_by("-created_at")
        .first()
    )
    if active is None:
        return {"running": False}
    return {
        "running": True,
        "since": active.created_at.isoformat(),
    }