from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import logging
import math
import numpy as np

from django.contrib.auth import get_user_model
from users.models import InterventionProposal
from app.models import InterventionScore, SelectionTool

User = get_user_model()
logger = logging.getLogger(__name__)


@dataclass
class CriteriaWeight:
    criteria_name: str
    total_score: int
    reviewer_count: int


@dataclass
class CriteriaAnchor:
    criteria_name: str
    worst_value: int
    best_value: int


@dataclass
class NormalisedScore:
    criteria_name: str
    normalised_value: float     # (total_score - worst) / (best - worst), None if unscored


@dataclass
class CriteriaStdDev:
    criteria_name: str
    std_dev: float              # SD of normalised values across all interventions


@dataclass
class InterventionWeight:
    intervention_id: str
    reference_number: str
    intervention_name: str
    criteria: list[CriteriaWeight] = field(default_factory=list)


@dataclass
class InterventionNormalised:
    intervention_id: str
    reference_number: str
    intervention_name: str
    normalised: list[NormalisedScore] = field(default_factory=list)


@dataclass
class WeightingReport:
    success: bool
    message: str
    anchors: list[CriteriaAnchor] = field(default_factory=list)
    interventions: list[InterventionWeight] = field(default_factory=list)
    normalisation_report: list[InterventionNormalised] = field(default_factory=list)
    standard_deviations: list[CriteriaStdDev] = field(default_factory=list)
    error: Optional[str] = None


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_score_index(interventions) -> dict[str, dict[str, list[int]]]:
    """{ intervention_id: { criteria_name: [score_values] } }"""
    index: dict[str, dict[str, list[int]]] = {}
    for s in InterventionScore.objects.select_related("criteria").filter(intervention__in=interventions):
        value = int(s.score.get("score_value", 0) if isinstance(s.score, dict) else s.score or 0)
        if value:
            index.setdefault(str(s.intervention_id), {}).setdefault(s.criteria.criteria.strip(), []).append(value)
    return index


# ── Computation helpers ───────────────────────────────────────────────────────

def _build_anchors(results: list[InterventionWeight], criteria_names: list[str]) -> list[CriteriaAnchor]:
    anchors = []
    for name in criteria_names:
        scored = [
            cw.total_score for iv in results
            for cw in iv.criteria
            if cw.criteria_name == name and cw.reviewer_count > 0
        ]
        anchors.append(CriteriaAnchor(
            criteria_name=name,
            worst_value=min(scored, default=0),
            best_value=max(scored, default=0),
        ))
    return anchors


def _normalise_value(total_score: int, worst: int, best: int) -> float:
    """(score - worst) / (best - worst). Returns 0.0 if scale is flat."""
    if best == worst:
        return 0.0
    return round((total_score - worst) / (best - worst), 4)


def _build_normalisation(
    results: list[InterventionWeight],
    anchors: list[CriteriaAnchor],
) -> list[InterventionNormalised]:
    anchor_map = {a.criteria_name: a for a in anchors}
    normalised_report = []
    for iv in results:
        scores = []
        for cw in iv.criteria:
            anchor = anchor_map[cw.criteria_name]
            # unscored cells get None — excluded from SD, shown as 0.0
            value = (
                _normalise_value(cw.total_score, anchor.worst_value, anchor.best_value)
                if cw.reviewer_count > 0 else 0.0
            )
            scores.append(NormalisedScore(criteria_name=cw.criteria_name, normalised_value=value))
        normalised_report.append(InterventionNormalised(
            intervention_id=iv.intervention_id,
            reference_number=iv.reference_number,
            intervention_name=iv.intervention_name,
            normalised=scores,
        ))
    return normalised_report


def _build_std_devs(
    normalisation_report: list[InterventionNormalised],
    criteria_names: list[str],
) -> list[CriteriaStdDev]:
    """Population SD (sigma) per criteria across all scored interventions."""
    std_devs = []
    for name in criteria_names:
        values = [
            ns.normalised_value for iv in normalisation_report
            for ns in iv.normalised
            if ns.criteria_name == name and ns.normalised_value is not None
        ]
        std_dev = round(float(np.std(values)), 9) if len(values) >= 2 else 0.0
        std_devs.append(CriteriaStdDev(criteria_name=name, std_dev=std_dev))
    return std_devs


# ── Service ───────────────────────────────────────────────────────────────────

class WeightingReportService:

    @staticmethod
    def generate(intervention_ids: list[str] | None = None) -> WeightingReport:
        try:
            qs = InterventionProposal.objects.order_by("reference_number")
            if intervention_ids:
                qs = qs.filter(id__in=intervention_ids)
            interventions = list(qs)

            criteria_names = list(
                SelectionTool.objects.values_list("criteria", flat=True).distinct().order_by("criteria")
            )
            score_index = _load_score_index(interventions)

            # 1. Raw scores
            results: list[InterventionWeight] = [
                InterventionWeight(
                    intervention_id=str(iv.id),
                    reference_number=getattr(iv, "reference_number", str(iv.id)),
                    intervention_name=getattr(iv, "intervention_name", str(iv)),
                    criteria=[
                        CriteriaWeight(
                            criteria_name=name,
                            total_score=sum(score_index.get(str(iv.id), {}).get(name, [])),
                            reviewer_count=len(score_index.get(str(iv.id), {}).get(name, [])),
                        )
                        for name in criteria_names
                    ],
                )
                for iv in interventions
            ]

            # 2. Anchors (worst/best per criteria, scored only)
            anchors = _build_anchors(results, criteria_names)

            # 3. Normalisation  — (score - worst) / (best - worst)
            normalisation_report = _build_normalisation(results, anchors)

            # 4. Standard deviation per criteria (population sigma)
            standard_deviations = _build_std_devs(normalisation_report, criteria_names)

            return WeightingReport(
                success=True,
                message="OK",
                anchors=anchors,
                interventions=results,
                normalisation_report=normalisation_report,
                standard_deviations=standard_deviations,
            )

        except Exception as exc:
            logger.exception("WeightingReportService.generate failed")
            return WeightingReport(success=False, message="Failed.", error=str(exc))
