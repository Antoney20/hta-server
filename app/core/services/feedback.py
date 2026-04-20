
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from django.core.cache import cache
from django.utils.timezone import now

from app.models import FeedbackCategory, InterventionStatusUpdate

logger = logging.getLogger(__name__)

CACHE_KEY     = "feedback:interventions:v1"
CACHE_TIMEOUT = 60 * 30  # 30 minutes



@dataclass
class InterventionFeedbackStatus:
    intervention_id:   str
    intervention_name: str
    reference_number:  str
    email:             str
    is_scored:         bool
    total_score:       int
    is_discussed:      bool          
    decision:          Optional[str] 
    decision_date:     Optional[str]
    feedback:          Optional[str]
    latest_status_update_id: Optional[str]


@dataclass
class BulkSendResult:
    success:   bool
    sent:      list[str] = field(default_factory=list)    # intervention ids
    failed:    list[str] = field(default_factory=list)
    errors:    dict[str, str] = field(default_factory=dict)
    total:     int = 0
    sent_count:   int = 0
    failed_count: int = 0



class FeedbackService:


    @staticmethod
    def invalidate():
        cache.delete(CACHE_KEY)

    @classmethod
    def _cached_statuses(cls) -> list[InterventionFeedbackStatus]:
        hit = cache.get(CACHE_KEY)
        if hit is not None:
            return hit
        result = cls._build_statuses()
        cache.set(CACHE_KEY, result, CACHE_TIMEOUT)
        return result

    @staticmethod
    def _build_statuses() -> list[InterventionFeedbackStatus]:
        from users.models import InterventionProposal
        from app.models import InterventionScore


        from django.db.models import Sum
        score_qs = (
            InterventionScore.objects
            .values("intervention_id")
            .annotate(total=Sum("score"))      
        )
        score_map: dict[str, int] = {
            str(r["intervention_id"]): (r["total"] or 0)
            for r in score_qs
        }


        status_qs = (
            InterventionStatusUpdate.objects
            .select_related("decision")
            .order_by("intervention_id", "-created_at")
        )
        latest_status: dict[str, InterventionStatusUpdate] = {}
        for su in status_qs:
            iid = str(su.intervention_id)
            if iid not in latest_status:
                latest_status[iid] = su

        proposals = (
            InterventionProposal.objects
            .only("id", "intervention_name", "reference_number", "email")
            .order_by("reference_number")
        )

        results: list[InterventionFeedbackStatus] = []
        for iv in proposals:
            iid       = str(iv.id)
            su        = latest_status.get(iid)
            total_sc  = score_map.get(iid, 0)

            results.append(InterventionFeedbackStatus(
                intervention_id=iid,
                intervention_name=getattr(iv, "intervention_name", str(iv)),
                reference_number=getattr(iv, "reference_number", ""),
                email=getattr(iv, "email", ""),
                is_scored=total_sc > 0,
                total_score=total_sc,
                is_discussed=su is not None,
                decision=str(su.decision) if su and su.decision else None,
                decision_date=su.decision_date.strftime("%d %B %Y") if su and su.decision_date else None,
                feedback=su.feedback or None if su else None,
                latest_status_update_id=str(su.id) if su else None,
            ))

        return results


    @classmethod
    def get_all_statuses(cls) -> list[InterventionFeedbackStatus]:
        return cls._cached_statuses()

    @classmethod
    def get_status(cls, intervention_id: str) -> Optional[InterventionFeedbackStatus]:
        return next(
            (s for s in cls._cached_statuses() if s.intervention_id == intervention_id),
            None,
        )


    @classmethod
    def bulk_send(
        cls,
        intervention_ids: list[str],
        category_id: str,
        sent_by=None,
    ) -> BulkSendResult:
        """
        Send a feedback email for each intervention_id using the given category.
        Cache is invalidated once after all sends, not per send.
        """
        from users.models import InterventionProposal
        from core.emails.feedback import send_feedback_email

        result = BulkSendResult(total=len(intervention_ids))

        # resolve category once
        try:
            category = FeedbackCategory.objects.get(pk=category_id, is_active=True)
        except FeedbackCategory.DoesNotExist:
            result.success = False
            for iid in intervention_ids:
                result.failed.append(iid)
                result.errors[iid] = "Category not found or inactive"
            result.failed_count = len(result.failed)
            return result

        # latest status update index (for enrichment)
        su_qs = (
            InterventionStatusUpdate.objects
            .filter(intervention_id__in=intervention_ids)
            .select_related("decision")
            .order_by("intervention_id", "-created_at")
        )
        latest_su: dict[str, InterventionStatusUpdate] = {}
        for su in su_qs:
            iid = str(su.intervention_id)
            if iid not in latest_su:
                latest_su[iid] = su

        # fetch all interventions in one query
        proposals = {
            str(iv.id): iv
            for iv in InterventionProposal.objects.filter(pk__in=intervention_ids)
        }

        for iid in intervention_ids:
            iv = proposals.get(iid)
            if not iv:
                result.failed.append(iid)
                result.errors[iid] = "Intervention not found"
                continue

            if not getattr(iv, "email", None):
                result.failed.append(iid)
                result.errors[iid] = "No email address on record"
                continue

            ok = send_feedback_email(
                intervention=iv,
                category=category,
                status_update=latest_su.get(iid),
                sent_by=sent_by,
            )
            if ok:
                result.sent.append(iid)
            else:
                result.failed.append(iid)
                result.errors[iid] = "Send failed — see email log"

        result.sent_count   = len(result.sent)
        result.failed_count = len(result.failed)
        result.success      = result.failed_count == 0

        cls.invalidate()

        return result