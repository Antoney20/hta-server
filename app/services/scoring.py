from django.contrib.auth import get_user_model
from dataclasses import dataclass, field
from typing import Optional
import logging

from users.models import InterventionProposal
from app.models import InterventionScore, SelectionTool

User = get_user_model()
logger = logging.getLogger(__name__)



@dataclass
class UserScoringStatus:
    user_id: int
    full_name: str
    email: str
    scored: bool
    score_count: int        # number of criteria this reviewer scored
    user_total_score: int   # sum of this reviewer's score_values for this intervention


@dataclass
class InterventionScoreReport:
    intervention_id: str
    reference_number: str
    intervention_name: str
    intervention_type: Optional[str]
    max_possible_score: int
    criteria_scored: int    # unique criteria names scored (by any reviewer)
    criteria_total: int     # total unique criteria available
    is_fully_scored: bool   # all criteria have been scored by at least one reviewer
    reviewer_statuses: list[UserScoringStatus] = field(default_factory=list)
    overall_total_score: int = 0  # sum of ALL score_values across ALL reviewers


@dataclass
class ScoringReportResult:
    success: bool
    message: str
    total_interventions: int = 0
    fully_scored: int = 0
    partially_scored: int = 0
    not_scored: int = 0
    total_reviewers: int = 0
    interventions: list[InterventionScoreReport] = field(default_factory=list)
    error: Optional[str] = None


# ─── Service ──────────────────────────────────────────────────────────────────

class ScoringReportService:
    """
    Generates structured scoring reports across all interventions.

    Score structure per InterventionScore row:
        score = {
            "tool_id": "<uuid>",
            "scoring_mechanism": "Effective",
            "score_value": 3,
            "criteria_label": "Clinical effectiveness, safety, and quality of the intervention."
        }

    Per intervention we return:
        - Each reviewer's score_count + user_total_score
        - overall_total_score = sum of all score_values from all reviewers
        - criteria_scored = number of unique criteria names covered

    Usage:
        result = ScoringReportService.generate()
        if result.success:
            for item in result.interventions:
                print(item.overall_total_score, item.reviewer_statuses)
    """

    @staticmethod
    def generate(intervention_ids: list[str] = None) -> ScoringReportResult:
        try:
            return ScoringReportService._build_report(intervention_ids)
        except Exception as exc:
            logger.exception("ScoringReportService failed")
            return ScoringReportResult(
                success=False,
                message="Failed to generate scoring report.",
                error=str(exc),
            )

    @staticmethod
    def _extract_score_value(score_field) -> int:
        """
        Extract integer score_value from the score JSONField.
        Handles: {"score_value": 3, ...} or plain int fallback.
        """
        if isinstance(score_field, dict):
            return int(score_field.get("score_value", 0))
        if isinstance(score_field, (int, float)):
            return int(score_field)
        return 0

    @staticmethod
    def _extract_criteria_label(score_field) -> str:
        """
        Extract criteria_label string from the score JSONField.
        e.g. "Clinical effectiveness, safety, and quality of the intervention."
        """
        if isinstance(score_field, dict):
            return score_field.get("criteria_label", "").strip()
        return ""

    @staticmethod
    def _build_report(intervention_ids: list[str] = None) -> ScoringReportResult:

        qs = InterventionProposal.objects.all()
        if intervention_ids:
            qs = qs.filter(id__in=intervention_ids)
        interventions = list(qs.order_by("reference_number"))

        reviewer_ids = (
            InterventionScore.objects
            .values_list("reviewer_id", flat=True)
            .distinct()
        )
        reviewers = list(User.objects.filter(id__in=reviewer_ids))

        # ── 3. Criteria — group SelectionTool rows by criteria name ───────────
        #    Each row = one scoring option (e.g. "Effective = 3")
        #    Unique criteria = unique `criteria` names
        #    Max per criteria = highest `scores` value in that group
        all_options = list(SelectionTool.objects.all().order_by("criteria", "-scores"))

        max_per_criteria_name: dict[str, int] = {}
        for opt in all_options:
            name = opt.criteria.strip()
            val = opt.scores if isinstance(opt.scores, int) else 0
            if name not in max_per_criteria_name or val > max_per_criteria_name[name]:
                max_per_criteria_name[name] = val

        criteria_count = len(max_per_criteria_name)           # e.g. 2
        max_possible = sum(max_per_criteria_name.values())    # e.g. 3 + 3 = 6

        # ── 4. All scores — single query ──────────────────────────────────────
        all_scores = list(
            InterventionScore.objects
            .select_related("reviewer")
            .filter(intervention__in=interventions)
        )

        # Index: { intervention_id → [InterventionScore, ...] }
        scores_by_intervention: dict[str, list] = {}
        for s in all_scores:
            key = str(s.intervention_id)
            scores_by_intervention.setdefault(key, []).append(s)

        # ── 5. Build per-intervention report ──────────────────────────────────
        reports: list[InterventionScoreReport] = []
        fully_scored_count = 0
        partially_scored_count = 0
        not_scored_count = 0

        for intervention in interventions:
            iid = str(intervention.id)
            scores = scores_by_intervention.get(iid, [])

            # ── Per-reviewer breakdown ────────────────────────────────────────
            scores_by_reviewer: dict[int, list] = {}
            for s in scores:
                scores_by_reviewer.setdefault(s.reviewer_id, []).append(s)

            reviewer_statuses: list[UserScoringStatus] = []
            overall_total_score = 0

            for reviewer in reviewers:
                reviewer_scores = scores_by_reviewer.get(reviewer.id, [])
                user_total = sum(
                    ScoringReportService._extract_score_value(s.score)
                    for s in reviewer_scores
                )
                overall_total_score += user_total

                reviewer_statuses.append(UserScoringStatus(
                    user_id=reviewer.id,
                    full_name= reviewer.username,
                    email=reviewer.email,
                    scored=len(reviewer_scores) > 0,
                    score_count=len(reviewer_scores),
                    user_total_score=user_total,
                ))

            # ── Unique criteria names covered (by any reviewer) ───────────────
            # Read criteria_label directly from the score JSON — no id lookup needed
            criteria_names_scored = {
                ScoringReportService._extract_criteria_label(s.score)
                for s in scores
                if ScoringReportService._extract_criteria_label(s.score)
            }
            criteria_scored = len(criteria_names_scored)
            is_fully_scored = criteria_scored >= criteria_count and criteria_count > 0

            report = InterventionScoreReport(
                intervention_id=iid,
                reference_number=getattr(intervention, "reference_number", iid),
                intervention_name=getattr(intervention, "intervention_name", str(intervention)),
                intervention_type=getattr(intervention, "intervention_type", None),
                max_possible_score=max_possible,
                criteria_scored=criteria_scored,
                criteria_total=criteria_count,
                is_fully_scored=is_fully_scored,
                reviewer_statuses=reviewer_statuses,
                overall_total_score=overall_total_score,
            )
            reports.append(report)

            if not scores:
                not_scored_count += 1
            elif is_fully_scored:
                fully_scored_count += 1
            else:
                partially_scored_count += 1

        # Sort: fully scored first → partial → none; descending score within each group
        reports.sort(key=lambda r: (-int(r.is_fully_scored), -r.overall_total_score))

        return ScoringReportResult(
            success=True,
            message="Report generated successfully.",
            total_interventions=len(reports),
            fully_scored=fully_scored_count,
            partially_scored=partially_scored_count,
            not_scored=not_scored_count,
            total_reviewers=len(reviewers),
            interventions=reports,
        )