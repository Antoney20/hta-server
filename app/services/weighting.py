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
class PearsonCell:
    criteria_name: str
    coefficient: float          # Pearson r, rounded to 4 dp


@dataclass
class PearsonRow:
    criteria_name: str
    correlations: list[PearsonCell] = field(default_factory=list)


@dataclass
class ConflictCell:
    criteria_name: str
    conflict_value: float       # 1 - r, rounded to 4 dp


@dataclass
class ConflictRow:
    criteria_name: str
    conflicts: list[ConflictCell] = field(default_factory=list)
    sum_of_conflict: float = 0.0


@dataclass
class CriteriaWeighting:
    criteria_name: str
    std_dev: float              # sigma, 4 dp
    sum_of_conflict: float      # 4 dp
    product: float              # sigma * sum_of_conflict, 4 dp
    weight: float               # product / total_product, 4 dp
    weight_percentage: float    # weight * 100, 4 dp


@dataclass
class WeightingReport:
    success: bool
    message: str
    anchors: list[CriteriaAnchor] = field(default_factory=list)
    interventions: list[InterventionWeight] = field(default_factory=list)
    normalisation_report: list[InterventionNormalised] = field(default_factory=list)
    standard_deviations: list[CriteriaStdDev] = field(default_factory=list)
    
    pearson_matrix: list[PearsonRow] = field(default_factory=list)
    conflict_matrix: list[ConflictRow] = field(default_factory=list)
    weightings: list[CriteriaWeighting] = field(default_factory=list)
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






# ─────────────────────────────────────────────────────────────────────────────
# UPDATE WeightingReport  (add three new fields)
# ─────────────────────────────────────────────────────────────────────────────


def _extract_normalised_matrix(
    normalisation_report: list[InterventionNormalised],
    criteria_names: list[str],
) -> np.ndarray:
    """
    Build a 2-D array shaped (n_interventions, n_criteria) from the
    normalisation report — ready for np.corrcoef.
    """
    rows = []
    for iv in normalisation_report:
        score_map = {ns.criteria_name: ns.normalised_value for ns in iv.normalised}
        rows.append([score_map.get(name, 0.0) for name in criteria_names])
    return np.array(rows, dtype=float)   # shape: (interventions, criteria)


def _build_pearson_matrix(
    normalisation_report: list[InterventionNormalised],
    criteria_names: list[str],
) -> list[PearsonRow]:
    """
    Step 4 – symmetric (n x n) Pearson correlation matrix.
    np.corrcoef expects variables as rows, so transpose the data matrix.
    """
    data = _extract_normalised_matrix(normalisation_report, criteria_names)
    # corrcoef wants shape (criteria, interventions)
    corr = np.corrcoef(data.T)          # shape: (n_criteria, n_criteria)

    pearson_rows = []
    for i, row_name in enumerate(criteria_names):
        cells = [
            PearsonCell(
                criteria_name=col_name,
                coefficient=round(float(corr[i, j]), 4),
            )
            for j, col_name in enumerate(criteria_names)
        ]
        pearson_rows.append(PearsonRow(criteria_name=row_name, correlations=cells))
    return pearson_rows


def _build_conflict_matrix(
    pearson_matrix: list[PearsonRow],
) -> list[ConflictRow]:
    """
    Step 5 – conflict matrix: each cell = 1 - Pearson_r.
    Sum each row to get the Sum of Conflict per criterion.
    """
    conflict_rows = []
    for pr in pearson_matrix:
        cells = [
            ConflictCell(
                criteria_name=cell.criteria_name,
                conflict_value=round(1.0 - cell.coefficient, 4),
            )
            for cell in pr.correlations
        ]
        row_sum = round(sum(c.conflict_value for c in cells), 4)
        conflict_rows.append(
            ConflictRow(
                criteria_name=pr.criteria_name,
                conflicts=cells,
                sum_of_conflict=row_sum,
            )
        )
    return conflict_rows


def _build_weightings(
    standard_deviations: list[CriteriaStdDev],
    conflict_rows: list[ConflictRow],
) -> list[CriteriaWeighting]:
    """
    Weighting (CRITIC method):
      product  = sigma  *  sum_of_conflict
      weight   = product / sum(all products)
      weight % = weight * 100
    All values rounded to 4 dp.
    """
    conflict_map = {cr.criteria_name: cr.sum_of_conflict for cr in conflict_rows}
    sigma_map    = {sd.criteria_name: round(sd.std_dev, 4) for sd in standard_deviations}

    # Build intermediate list with products
    entries = []
    for sd in standard_deviations:
        name    = sd.criteria_name
        sigma   = sigma_map[name]
        soc     = conflict_map.get(name, 0.0)
        product = round(sigma * soc, 4)
        entries.append((name, sigma, soc, product))

    total_product = round(sum(e[3] for e in entries), 4)

    weightings = []
    for name, sigma, soc, product in entries:
        weight     = round(product / total_product, 4) if total_product else 0.0
        weight_pct = round(weight * 100, 4)
        weightings.append(CriteriaWeighting(
            criteria_name    = name,
            std_dev          = sigma,
            sum_of_conflict  = soc,
            product          = product,
            weight           = weight,
            weight_percentage= weight_pct,
        ))
    return weightings



class WeightingReportService:

    @staticmethod
    def generate(intervention_ids: list[str] | None = None) -> WeightingReport:
        try:
            qs = InterventionProposal.objects.order_by("reference_number")
            if intervention_ids:
                qs = qs.filter(id__in=intervention_ids)
            interventions = list(qs)

            criteria_names = list(
                SelectionTool.objects.values_list("criteria", flat=True)
                .distinct().order_by("criteria")
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

            # 2. Anchors (worst / best per criteria)
            anchors = _build_anchors(results, criteria_names)

            # 3. Normalisation — (score - worst) / (best - worst)
            normalisation_report = _build_normalisation(results, anchors)

            # 4. Standard deviation per criteria (population sigma), 4 dp
            standard_deviations = _build_std_devs(normalisation_report, criteria_names)

            # 5. Pearson correlation matrix (n x n)
            pearson_matrix = _build_pearson_matrix(normalisation_report, criteria_names)

            # 6. Conflict matrix: 1 - r, with row Sum of Conflict
            conflict_matrix = _build_conflict_matrix(pearson_matrix)

            # 7. CRITIC weightings: sigma * sum_of_conflict → normalise → %
            weightings = _build_weightings(standard_deviations, conflict_matrix)

            return WeightingReport(
                success=True,
                message="OK",
                anchors=anchors,
                interventions=results,
                normalisation_report=normalisation_report,
                standard_deviations=standard_deviations,
                pearson_matrix=pearson_matrix,
                conflict_matrix=conflict_matrix,
                weightings=weightings,
            )

        except Exception as exc:
            logger.exception("WeightingReportService.generate failed")
            return WeightingReport(success=False, message="Failed.", error=str(exc))