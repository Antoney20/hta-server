"""
Panel Appraisal Scoring Service
Handles CriteriaAppraisalScore creation for interventions moved to panel.
"""

from django.db import transaction
from django.core.exceptions import ValidationError
from rest_framework.exceptions import PermissionDenied

from app.models import CriteriaAppraisalScore, CriteriaAppraisalTool, InterventionStatusUpdate
from users.models import UserRole



def _assert_can_score(user) -> None:
    """Only PANEL members and admins may submit scores."""
    if user.role not in (UserRole.PANEL, UserRole.ADMIN):
        raise PermissionDenied("Only panel members and admins can submit scores.")


def _assert_can_view(user) -> None:
    """PANEL, ADMIN, and SECRETARIAT may view scores."""
    allowed = (UserRole.PANEL, UserRole.ADMIN, UserRole.SECRETARIAT)
    if user.role not in allowed:
        raise PermissionDenied("Access restricted to panel, admin, or secretariat.")



def get_panel_interventions():
    """
    Return InterventionStatusUpdate rows where move_to_panel=True.
    One row per intervention (latest update wins).
    """
    return (
        InterventionStatusUpdate.objects
        .filter(move_to_panel=True)
        .select_related("intervention", "decision", "updated_by")
        .order_by("intervention_id", "-created_at")
        .distinct("intervention_id")   # postgres distinct-on
    )


def get_panel_intervention_ids() -> list:
    return list(
        get_panel_interventions().values_list("intervention_id", flat=True)
    )



def get_scores_for_user(user, intervention_id=None):
    """All appraisal scores submitted by *user*, optionally filtered."""
    qs = (
        CriteriaAppraisalScore.objects
        .select_related("reviewer", "intervention", "criteria", "rescored_by")
        .filter(reviewer=user)
    )
    if intervention_id:
        qs = qs.filter(intervention_id=intervention_id)
    return qs


def get_all_scores(intervention_id=None):
    """All scores across all reviewers (admin/secretariat view)."""
    qs = CriteriaAppraisalScore.objects.select_related(
        "reviewer", "intervention", "criteria", "rescored_by"
    )
    if intervention_id:
        qs = qs.filter(intervention_id=intervention_id)
    return qs


# ── single score ──────────────────────────────────────────────────────────────

def create_score(user, intervention_id: str, criteria_id: str, score: dict, comment: str = "") -> CriteriaAppraisalScore:
    """
    Create a single appraisal score. Raises if already scored (use rescore instead).
    intervention must have move_to_panel=True.
    """
    _assert_can_score(user)

    if intervention_id not in get_panel_intervention_ids():
        raise ValidationError("Intervention has not been moved to panel.")

    if CriteriaAppraisalScore.objects.filter(
        reviewer=user, intervention_id=intervention_id, criteria_id=criteria_id
    ).exists():
        raise ValidationError(
            "Score already exists for this criterion. Use rescore endpoint."
        )

    return CriteriaAppraisalScore.objects.create(
        reviewer=user,
        intervention_id=intervention_id,
        criteria_id=criteria_id,
        score=score,
        comment=comment,
    )


# ── bulk score (atomic) ───────────────────────────────────────────────────────

def bulk_create_scores(user, intervention_id: str, items: list[dict]) -> list[CriteriaAppraisalScore]:
    """
    Atomically create scores for multiple criteria on one intervention.

    items = [{"criteria_id": "...", "score": {...}, "comment": "..."}, ...]

    All succeed or all fail — no partial saves.
    Duplicate criteria within the batch or against existing rows raise ValidationError.
    """
    _assert_can_score(user)

    if intervention_id not in get_panel_intervention_ids():
        raise ValidationError("Intervention has not been moved to panel.")

    # detect intra-batch duplicates
    criteria_ids = [i["criteria_id"] for i in items]
    if len(criteria_ids) != len(set(criteria_ids)):
        raise ValidationError("Duplicate criteria IDs in the same batch.")

    # detect existing scores
    existing = set(
        CriteriaAppraisalScore.objects
        .filter(
            reviewer=user,
            intervention_id=intervention_id,
            criteria_id__in=criteria_ids,
        )
        .values_list("criteria_id", flat=True)
    )
    if existing:
        raise ValidationError(
            f"Scores already exist for criteria: {list(existing)}. Use rescore endpoint."
        )

    # validate criteria exist
    found_ids = set(
        CriteriaAppraisalTool.objects
        .filter(id__in=criteria_ids)
        .values_list("id", flat=True)
    )
    missing = set(criteria_ids) - found_ids
    if missing:
        raise ValidationError(f"Unknown criteria IDs: {list(missing)}")

    with transaction.atomic():
        created = [
            CriteriaAppraisalScore(
                reviewer=user,
                intervention_id=intervention_id,
                criteria_id=item["criteria_id"],
                score=item["score"],
                comment=item.get("comment", ""),
            )
            for item in items
        ]
        return CriteriaAppraisalScore.objects.bulk_create(created)

