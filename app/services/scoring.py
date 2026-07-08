from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import logging

from django.contrib.auth import get_user_model
from django.db.models import Q

from users.models import InterventionProposal
from app.models import InterventionScore, SelectionTool, NationalProgramProposal

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class CriteriaScore:
    criteria_name: str
    score_value: int
    notes: Optional[str] = None


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
    target_type: str                      # "intervention" | "national_proposal"
    reference_number: str
    intervention_name: str
    intervention_type: Optional[str]
    system_categories: list[str]
    total_score: int
    criteria_scored: int
    criteria_total: int
    package: Optional[str]
    phase: Optional[str]
    scored_at: Optional[str] = None
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
    total_reviewers: int = 0
    by_category: list[CategoryGroup] = field(default_factory=list)
    error: Optional[str] = None



@dataclass
class TargetMeta:
    """Normalized view of an intervention OR national proposal for reporting."""
    id: str
    target_type: str                      # "intervention" | "national_proposal"
    reference_number: str
    name: str
    intervention_type: Optional[str]
    system_categories: list[str]
    package: Optional[str]
    phase: Optional[str]


def _intervention_meta(iv: InterventionProposal) -> TargetMeta:
    return TargetMeta(
        id=str(iv.id),
        target_type="intervention",
        reference_number=iv.reference_number or str(iv.id),
        name=iv.intervention_name or str(iv),
        intervention_type=getattr(iv, "intervention_type", None),
        system_categories=[sc.system_category.name for sc in iv.system_categories.all()],
        package=iv.package.name if iv.package_id else None,
        phase=iv.phase.name if iv.phase_id else None,
    )


def _national_meta(np: NationalProgramProposal) -> TargetMeta:
    return TargetMeta(
        id=str(np.id),
        target_type="national_proposal",
        reference_number=np.reference_number or str(np.id),
        name=np.title or str(np),
        intervention_type=None,                    # nationals have no intervention_type
        system_categories=[],                      # nationals aren't system-categorized
        package=np.package.name if np.package_id else None,
        phase=np.phase.name if np.phase_id else None,
    )



class ScoringReportService:
    """
    Builds a scoring report grouped by system category, covering BOTH
    intervention proposals and national program proposals.

    Only includes targets that have at least one score (total_score > 0).
    National proposals have no system categories, so they group under
    'National Programs'.
    """

    @staticmethod
    def generate(intervention_ids: list[str] | None = None) -> ScoringReport:
        try:
            return ScoringReportService._build(intervention_ids)
        except Exception as exc:
            logger.exception("ScoringReportService.generate failed")
            return ScoringReport(success=False, message="Report generation failed.", error=str(exc))

    @staticmethod
    def _score_value(score) -> int:
        if isinstance(score, dict):
            return int(score.get("score_value", 0))
        return int(score) if isinstance(score, (int, float)) else 0

    @staticmethod
    def _build(target_ids: list[str] | None) -> ScoringReport:
        # 1. Load BOTH target types, build one meta map keyed by id
        iv_qs = (
            InterventionProposal.objects
            .select_related("package", "phase")
            .prefetch_related("system_categories__system_category")
            .order_by("reference_number")
        )
        np_qs = (
            NationalProgramProposal.objects
            .select_related("package", "phase")
            .order_by("reference_number")
        )
        if target_ids:
            iv_qs = iv_qs.filter(id__in=target_ids)
            np_qs = np_qs.filter(id__in=target_ids)

        meta_map: dict[str, TargetMeta] = {}
        for iv in iv_qs:
            meta_map[str(iv.id)] = _intervention_meta(iv)
        for np in np_qs:
            meta_map[str(np.id)] = _national_meta(np)

        all_target_ids = list(meta_map.keys())

        # 2. Unique criteria names
        all_criteria_names: list[str] = list(
            SelectionTool.objects
            .values_list("criteria", flat=True)
            .distinct()
            .order_by("criteria")
        )

        # 3. Reviewers — anyone who has ever scored (either target type)
        reviewer_ids = InterventionScore.objects.values_list("reviewer_id", flat=True).distinct()
        reviewers = list(User.objects.filter(id__in=reviewer_ids))

        # 4. Score index: { target_id: { reviewer_id: { criteria_name: {...} } } }
        #    Scores are matched by EITHER FK — coalesce to a single target id.
        score_index: dict[str, dict[int, dict[str, dict[str, Optional[str]]]]] = {}
        scored_index: dict[str, str] = {}

        score_qs = (
            InterventionScore.objects
            .select_related("reviewer", "criteria")
            .filter(
                Q(intervention_id__in=all_target_ids)
                | Q(national_proposal_id__in=all_target_ids)
            )
            .order_by("created_at")
        )

        for s in score_qs:
            # coalesce whichever FK is set → the target id
            tid = str(s.intervention_id or s.national_proposal_id)
            if tid not in meta_map:
                continue
            cname = s.criteria.criteria.strip()

            (
                score_index
                .setdefault(tid, {})
                .setdefault(s.reviewer_id, {})
            )[cname] = {
                "score_value": ScoringReportService._score_value(s.score),
                "notes": s.comment.strip() if s.comment else None,
            }

            if tid not in scored_index:
                scored_index[tid] = s.created_at.isoformat()

        # 5. Build per-target reports — skip targets with total_score == 0
        reports: list[InterventionReport] = []

        for tid in all_target_ids:
            meta = meta_map[tid]
            iv_scores = score_index.get(tid, {})

            reviewer_statuses: list[ReviewerStatus] = []
            unscored: list[ReviewerStatus] = []
            total_score = 0
            scored_criteria: set[str] = set()

            for r in reviewers:
                r_criteria_map = iv_scores.get(r.id, {})

                criteria_scores = []
                for name in all_criteria_names:
                    entry = r_criteria_map.get(name, {})
                    criteria_scores.append(
                        CriteriaScore(
                            criteria_name=name,
                            score_value=entry.get("score_value", 0),
                            notes=entry.get("notes"),
                        )
                    )

                r_total = sum(cs.score_value for cs in criteria_scores)
                total_score += r_total
                scored_criteria.update(r_criteria_map.keys())

                status = ReviewerStatus(
                    user_id=r.id,
                    full_name=r.username,
                    email=r.email,
                    scored=bool(r_criteria_map),
                    score_count=len(r_criteria_map),
                    total_score=r_total,
                    criteria_scores=criteria_scores,
                )
                reviewer_statuses.append(status)
                if not r_criteria_map:
                    unscored.append(status)

            if total_score == 0:
                continue

            reports.append(InterventionReport(
                intervention_id=tid,
                target_type=meta.target_type,
                reference_number=meta.reference_number,
                intervention_name=meta.name,
                intervention_type=meta.intervention_type,
                system_categories=meta.system_categories,
                scored_at=scored_index.get(tid),
                total_score=total_score,
                package=meta.package,
                phase=meta.phase,
                criteria_scored=len(scored_criteria),
                criteria_total=len(all_criteria_names),
                reviewers=reviewer_statuses,
                unscored_reviewers=unscored,
            ))

        # 6. Group by system category (nationals → 'National Programs')
        category_map: dict[str, list[InterventionReport]] = {}
        for ir in reports:
            cats = ir.system_categories
            if not cats:
                cats = ["National Programs"] if ir.target_type == "national_proposal" else ["Uncategorized"]
            for cat in cats:
                category_map.setdefault(cat, []).append(ir)

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
            total_interventions=len(reports),
            total_reviewers=len(reviewers),
            by_category=by_category,
        )