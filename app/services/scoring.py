from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import logging

from django.contrib.auth import get_user_model

from users.models import InterventionProposal
from app.models import InterventionScore, SelectionTool

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Data shapes ───────────────────────────────────────────────────────────────

@dataclass
class CriteriaScore:
    criteria_name: str
    score_value: int            # 0 if not scored


@dataclass
class ReviewerStatus:
    user_id: int
    full_name: str
    email: str
    scored: bool
    score_count: int
    total_score: int
    criteria_scores: list[CriteriaScore] = field(default_factory=list)


@dataclass
class InterventionReport:
    intervention_id: str
    reference_number: str
    intervention_name: str
    intervention_type: Optional[str]
    system_categories: list[str]
    total_score: int
    criteria_scored: int        # unique criteria scored by any reviewer
    criteria_total: int         # total criteria available
    reviewers: list[ReviewerStatus] = field(default_factory=list)
    unscored_reviewers: list[ReviewerStatus] = field(default_factory=list)


@dataclass
class CategoryGroup:
    category: str
    interventions: list[InterventionReport] = field(default_factory=list)


@dataclass
class ScoringReport:
    success: bool
    message: str
    total_interventions: int = 0
    not_scored: int = 0
    total_reviewers: int = 0
    by_category: list[CategoryGroup] = field(default_factory=list)
    error: Optional[str] = None


# ── Service ───────────────────────────────────────────────────────────────────

class ScoringReportService:
    """
    Builds a scoring report grouped by system category.

    Each InterventionReport contains:
      - reviewers: all reviewers with per-criteria breakdown + totals
      - unscored_reviewers: reviewers who haven't scored this intervention at all

    Score JSON shape (InterventionScore.score):
        {"tool_id": "...", "score_value": 3, "criteria_label": "Clinical effectiveness..."}

    Criteria come from SelectionTool — these are the canonical scoring dimensions.
    Each reviewer's criteria_scores list always contains ALL criteria (score_value=0 if not yet scored).

    Usage:
        report = ScoringReportService.generate()
    """

    @staticmethod
    def generate(intervention_ids: list[str] | None = None) -> ScoringReport:
        try:
            return ScoringReportService._build(intervention_ids)
        except Exception as exc:
            logger.exception("ScoringReportService.generate failed")
            return ScoringReport(success=False, message="Report generation failed.", error=str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _score_value(score) -> int:
        if isinstance(score, dict):
            return int(score.get("score_value", 0))
        return int(score) if isinstance(score, (int, float)) else 0

    # ── Core ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build(intervention_ids: list[str] | None) -> ScoringReport:
        # 1. Interventions
        qs = (
            InterventionProposal.objects
            .prefetch_related("system_categories__system_category")
            .order_by("reference_number")
        )
        if intervention_ids:
            qs = qs.filter(id__in=intervention_ids)
        interventions = list(qs)

        # 2. Unique criteria names — SelectionTool rows are scoring OPTIONS (e.g. Effective=3, Moderate=2)
        #    grouped under the same criteria name. We want one entry per unique name.
        all_criteria_names: list[str] = list(
            SelectionTool.objects
            .values_list("criteria", flat=True)
            .distinct()
            .order_by("criteria")
        )
        criteria_total = len(all_criteria_names)

        # 3. Reviewers — anyone who has ever scored
        reviewer_ids = InterventionScore.objects.values_list("reviewer_id", flat=True).distinct()
        reviewers = list(User.objects.filter(id__in=reviewer_ids))

        # 4. All scores — indexed by (intervention_id, reviewer_id, criteria_name)
        #    InterventionScore.criteria FK → SelectionTool, which has a .criteria name field
        all_scores = list(
            InterventionScore.objects
            .select_related("reviewer", "criteria")
            .filter(intervention__in=interventions)
        )
        # { intervention_id: { reviewer_id: { criteria_name: score_value } } }
        score_index: dict[str, dict[int, dict[str, int]]] = {}
        for s in all_scores:
            iid = str(s.intervention_id)
            criteria_name = s.criteria.criteria.strip()
            score_index \
                .setdefault(iid, {}) \
                .setdefault(s.reviewer_id, {})[criteria_name] = ScoringReportService._score_value(s.score)

        # 5. Build per-intervention reports
        not_scored = 0
        reports: list[InterventionReport] = []

        for iv in interventions:
            iid = str(iv.id)
            iv_scores = score_index.get(iid, {})  # { reviewer_id: { criteria_id: value } }

            reviewer_statuses: list[ReviewerStatus] = []
            unscored: list[ReviewerStatus] = []
            total_score = 0
            all_criteria_ids_scored: set[str] = set()

            for r in reviewers:
                r_criteria_map = iv_scores.get(r.id, {})   # { criteria_id: value }

                # One entry per unique criteria name — score_value 0 if not scored
                criteria_scores = [
                    CriteriaScore(
                        criteria_name=name,
                        score_value=r_criteria_map.get(name, 0),
                    )
                    for name in all_criteria_names
                ]

                r_total = sum(cs.score_value for cs in criteria_scores)
                total_score += r_total
                all_criteria_ids_scored.update(r_criteria_map.keys())

                status = ReviewerStatus(
                    user_id=r.id,
                    full_name= r.username,
                    email=r.email,
                    scored=bool(r_criteria_map),
                    score_count=len(r_criteria_map),
                    total_score=r_total,
                    criteria_scores=criteria_scores,
                )
                reviewer_statuses.append(status)
                if not r_criteria_map:
                    unscored.append(status)

            if not iv_scores:
                not_scored += 1

            reports.append(InterventionReport(
                intervention_id=iid,
                reference_number=getattr(iv, "reference_number", iid),
                intervention_name=getattr(iv, "intervention_name", str(iv)),
                intervention_type=getattr(iv, "intervention_type", None),
                system_categories=[
                    sc.system_category.name for sc in iv.system_categories.all()
                ],
                total_score=total_score,
                criteria_scored=len(all_criteria_ids_scored),
                criteria_total=criteria_total,
                reviewers=reviewer_statuses,
                unscored_reviewers=unscored,
            ))

        # 6. Group by system category
        category_map: dict[str, list[InterventionReport]] = {}
        for ir in reports:
            if ir.system_categories:
                for cat in ir.system_categories:
                    category_map.setdefault(cat, []).append(ir)
            else:
                category_map.setdefault("Uncategorized", []).append(ir)

        by_category = [
            CategoryGroup(
                category=cat,
                interventions=sorted(ivs, key=lambda x: -x.total_score),
            )
            for cat, ivs in sorted(category_map.items())
        ]

        return ScoringReport(
            success=True,
            message="Report generated successfully.",
            total_interventions=len(interventions),
            not_scored=not_scored,
            total_reviewers=len(reviewers),
            by_category=by_category,
        )