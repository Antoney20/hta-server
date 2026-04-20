from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from django.core.cache import cache

from app.core.emails.feedback import send_feedback_email
from app.models import InterventionSystemCategory

logger = logging.getLogger(__name__)

CACHE_KEY     = "feedback:interventions:v1"
CACHE_TIMEOUT = 60 * 30


@dataclass
class InterventionFeedbackStatus:
    intervention_id:         str
    intervention_name:       str
    reference_number:        str
    email:                   str
    submitted_at:            Optional[str]
    system_categories:       list[str]
    has_feedback_sent:       bool
    feedback_sent_count:     int
    last_feedback_sent_at:   Optional[str]
    is_scored:               bool
    total_score:             int
    is_discussed:            bool
    decision:                Optional[str]
    decision_date:           Optional[str]
    feedback:                Optional[str]
    latest_status_update_id: Optional[str]


@dataclass
class SendResult:
    """Result for a single email send attempt."""
    intervention_id: str
    success:         bool
    error:           Optional[str] = None


@dataclass
class BulkSendResult:
    """Aggregated result across one or more send attempts."""
    total:        int = 0
    sent:         list[str] = field(default_factory=list)
    failed:       list[str] = field(default_factory=list)
    errors:       dict[str, str] = field(default_factory=dict)
    sent_count:   int = 0
    failed_count: int = 0

    @property
    def success(self) -> bool:
        """All attempted sends succeeded."""
        return self.sent_count > 0 and self.failed_count == 0

    @property
    def partial(self) -> bool:
        """Some succeeded, some failed."""
        return self.sent_count > 0 and self.failed_count > 0

    @property
    def all_failed(self) -> bool:
        """Every attempt failed."""
        return self.sent_count == 0 and self.failed_count > 0

    @property
    def summary(self) -> str:
        if self.success:
            return f"All {self.sent_count} email(s) sent successfully."
        if self.partial:
            return f"Partially sent: {self.sent_count}/{self.total}. {self.failed_count} failed."
        return f"All {self.total} email(s) failed to send."

    def record(self, result: SendResult) -> None:
        """Register a single SendResult into this aggregate."""
        if result.success:
            self.sent.append(result.intervention_id)
            self.sent_count += 1
        else:
            self.failed.append(result.intervention_id)
            self.errors[result.intervention_id] = result.error or "Unknown error"
            self.failed_count += 1


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
        from app.models import (
            InterventionScore, InterventionStatusUpdate,
            FeedbackEmailLog, InterventionSystemCategory,
        )
        from django.db.models import Count, Max

        _raw_scores = (
            InterventionScore.objects
            .values("intervention_id", "score")
        )
        score_map: dict[str, int] = {}
        for row in _raw_scores:
            iid = str(row["intervention_id"])
            val = row["score"]
            if isinstance(val, dict):
                sv = int(val.get("score_value", 0) or 0)
            elif isinstance(val, (int, float)):
                sv = int(val)
            else:
                sv = 0
            score_map[iid] = score_map.get(iid, 0) + sv

        # ── latest status update per intervention ─────────────────────
        latest_status: dict[str, object] = {}
        for su in (
            InterventionStatusUpdate.objects
            .select_related("decision")
            .order_by("intervention_id", "-created_at")
        ):
            iid = str(su.intervention_id)
            if iid not in latest_status:
                latest_status[iid] = su

        # ── feedback log aggregates ───────────────────────────────────
        log_agg: dict[str, dict] = {}
        for row in (
            FeedbackEmailLog.objects
            .values("intervention_id")
            .annotate(count=Count("id"), last_sent=Max("created_at"))
        ):
            log_agg[str(row["intervention_id"])] = {
                "count":     int(row["count"]),
                "last_sent": row["last_sent"].isoformat() if row["last_sent"] else None,
            }

        # ── system category names per intervention ────────────────────
        cat_map: dict[str, list[str]] = {}
        for isc in (
            InterventionSystemCategory.objects
            .select_related("system_category")
            .only("intervention_id", "system_category__name")
        ):
            cat_map.setdefault(str(isc.intervention_id), []).append(
                isc.system_category.name
            )

        # ── proposals ─────────────────────────────────────────────────
        proposals = (
            InterventionProposal.objects
            .only("id", "intervention_name", "reference_number", "email", "submitted_at")
            .order_by("reference_number")
        )

        results: list[InterventionFeedbackStatus] = []
        for iv in proposals:
            iid      = str(iv.id)
            su       = latest_status.get(iid)
            total_sc = score_map.get(iid, 0)
            logs     = log_agg.get(iid, {})
            submitted = getattr(iv, "submitted_at", None)

            results.append(InterventionFeedbackStatus(
                intervention_id=iid,
                intervention_name=getattr(iv, "intervention_name", str(iv)),
                reference_number=getattr(iv, "reference_number", ""),
                email=getattr(iv, "email", ""),
                submitted_at=submitted.isoformat() if submitted else None,
                system_categories=cat_map.get(iid, []),
                has_feedback_sent=bool(logs),
                feedback_sent_count=logs.get("count", 0),
                last_feedback_sent_at=logs.get("last_sent"),
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
    def get_all_statuses(
        cls,
        date_from: str | None = None,
        date_to:   str | None = None,
    ) -> list[InterventionFeedbackStatus]:
        statuses = cls._cached_statuses()
        if date_from:
            statuses = [s for s in statuses if s.submitted_at and s.submitted_at >= date_from]
        if date_to:
            statuses = [s for s in statuses if s.submitted_at and s.submitted_at <= date_to + "T23:59:59"]
        return statuses

    @classmethod
    def get_status(cls, intervention_id: str) -> Optional[InterventionFeedbackStatus]:
        return next(
            (s for s in cls._cached_statuses() if s.intervention_id == intervention_id),
            None,
        )

    # ── core single send ──────────────────────────────────────────────
    @classmethod
    def _send_one(
        cls,
        iid: str,
        proposals: dict,
        latest_su: dict,
        category,
        sent_by=None,
    ) -> SendResult:
        """Attempt to send feedback email for a single intervention. Never raises."""
        iv = proposals.get(iid)
        if not iv:
            return SendResult(iid, success=False, error="Intervention not found")
        if not getattr(iv, "email", None):
            return SendResult(iid, success=False, error="No email address")
        try:
            ok = send_feedback_email(
                intervention=iv,
                category=category,
                status_update=latest_su.get(iid),
                sent_by=sent_by,
            )
            if ok:
                return SendResult(iid, success=True)
            return SendResult(iid, success=False, error="Send failed — see email log")
        except Exception as exc:
            logger.exception("Unexpected error sending feedback email for %s", iid)
            return SendResult(iid, success=False, error=str(exc))

    # ── public: single send ───────────────────────────────────────────
    @classmethod
    def send(
        cls,
        intervention_id: str,
        category_id: str,
        sent_by=None,
    ) -> SendResult:
        from users.models import InterventionProposal
        from app.models import FeedbackCategory, InterventionStatusUpdate

        try:
            category = FeedbackCategory.objects.get(pk=category_id, is_active=True)
        except FeedbackCategory.DoesNotExist:
            return SendResult(intervention_id, success=False, error="Category not found or inactive")

        proposals = {
            str(iv.id): iv
            for iv in InterventionProposal.objects.filter(pk=intervention_id)
        }

        latest_su: dict[str, object] = {}
        for su in (
            InterventionStatusUpdate.objects
            .filter(intervention_id=intervention_id)
            .select_related("decision")
            .order_by("-created_at")[:1]
        ):
            latest_su[str(su.intervention_id)] = su

        result = cls._send_one(intervention_id, proposals, latest_su, category, sent_by)
        cls.invalidate()
        return result

    @classmethod
    def bulk_send(
        cls,
        intervention_ids: list[str],
        category_id: str,
        sent_by=None,
    ) -> BulkSendResult:
        from users.models import InterventionProposal
        from app.models import FeedbackCategory, InterventionStatusUpdate

        aggregate = BulkSendResult(total=len(intervention_ids))

        try:
            category = FeedbackCategory.objects.get(pk=category_id, is_active=True)
        except FeedbackCategory.DoesNotExist:
            for iid in intervention_ids:
                aggregate.record(SendResult(iid, success=False, error="Category not found or inactive"))
            return aggregate

        latest_su: dict[str, object] = {}
        for su in (
            InterventionStatusUpdate.objects
            .filter(intervention_id__in=intervention_ids)
            .select_related("decision")
            .order_by("intervention_id", "-created_at")
        ):
            iid = str(su.intervention_id)
            if iid not in latest_su:
                latest_su[iid] = su

        proposals = {
            str(iv.id): iv
            for iv in InterventionProposal.objects.filter(pk__in=intervention_ids)
        }

        for iid in intervention_ids:
            aggregate.record(
                cls._send_one(iid, proposals, latest_su, category, sent_by)
            )

        cls.invalidate()
        return aggregate

    @classmethod
    def resend(cls, log_id: str, sent_by=None) -> SendResult:
        from app.models import FeedbackEmailLog

        try:
            log = (
                FeedbackEmailLog.objects
                .select_related("intervention", "category")
                .get(pk=log_id)
            )
        except FeedbackEmailLog.DoesNotExist:
            return SendResult(log_id, success=False, error="Email log not found")

        if not log.category.is_active:
            return SendResult(str(log.intervention_id), success=False, error="Category is inactive — cannot resend")

        iid = str(log.intervention_id)
        proposals  = {iid: log.intervention}
        latest_su  = {}  # resend does not re-attach a status update

        result = cls._send_one(iid, proposals, latest_su, log.category, sent_by)
        cls.invalidate()
        return result