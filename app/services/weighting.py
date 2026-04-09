from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import logging
import numpy as np

from django.contrib.auth import get_user_model
from users.models import InterventionProposal
from app.models import InterventionScore, SelectionTool

User = get_user_model()
logger = logging.getLogger(__name__)

# ── Score scale constants ─────────────────────────────────────────────────────

SCORE_MIN = 1   # worst possible score a reviewer can give
SCORE_MAX = 3   # best possible score a reviewer can give


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class CriteriaAnchor:
    criteria_name: str
    worst_value: float
    best_value: float


@dataclass
class NormalisedScore:
    criteria_name: str
    normalised_value: Optional[float]   # None if reviewer did not score this cell


@dataclass
class InterventionNormalised:
    intervention_id: str
    intervention_name: str
    normalised: list[NormalisedScore] = field(default_factory=list)


@dataclass
class CriteriaStdDev:
    criteria_name: str
    std_dev: float   # population SD (sigma) of normalised values across interventions


@dataclass
class PearsonCell:
    criteria_name: str
    coefficient: float   # Pearson r, rounded to 4 dp


@dataclass
class PearsonRow:
    criteria_name: str
    correlations: list[PearsonCell] = field(default_factory=list)


@dataclass
class ConflictCell:
    criteria_name: str
    conflict_value: float   # 1 - r, rounded to 4 dp


@dataclass
class ConflictRow:
    criteria_name: str
    conflicts: list[ConflictCell] = field(default_factory=list)
    sum_of_conflict: float = 0.0


@dataclass
class CriteriaWeighting:
    """
    Per-reviewer CRITIC weighting for one criteria.

        product         = sd * sum_of_conflict
        sum_of_products = sum of product across ALL criteria (this reviewer)
        weight          = product / sum_of_products
        weight_%        = weight * 100
    """
    criteria_name: str
    std_dev: float
    sum_of_conflict: float
    product: float
    sum_of_products: float
    weight: float
    weight_percentage: float


@dataclass
class ReviewerWeightingResult:
    """
    Full CRITIC pipeline output for one reviewer.
    reviewer_id is the UUID string only.
    """
    reviewer_id: str
    reviewer_email: Optional[str] = None
    reviewer_username: Optional[str] = None
    anchors: list[CriteriaAnchor] = field(default_factory=list)
    normalisation_report: list[InterventionNormalised] = field(default_factory=list)
    standard_deviations: list[CriteriaStdDev] = field(default_factory=list)
    pearson_matrix: list[PearsonRow] = field(default_factory=list)
    conflict_matrix: list[ConflictRow] = field(default_factory=list)
    weightings: list[CriteriaWeighting] = field(default_factory=list)


# ── Scoring dataclasses ───────────────────────────────────────────────────────

@dataclass
class CriteriaWeightedScore:
    """
    One criteria contribution for a reviewer × intervention.
    weighted_score = raw_score * weight
    """
    criteria_name: str
    raw_score: int
    weight: float
    weighted_score: float


# @dataclass
# class ReviewerInterventionScore:
#     """
#     One reviewer × one intervention.

#     criteria_scores  = list of per-criteria (raw_score * weight) detail
#     total_score      = sum of weighted_scores across all scored criteria
#                        (used for individual ranking)
#     """
#     reviewer_id: str
#     reviewer_email: Optional[str]
#     reviewer_username: Optional[str]
#     intervention_id: str
#     intervention_name: str
#     # criteria_scores: list[CriteriaWeightedScore] = field(default_factory=list)
#     weighted_criteria: dict[str, float] = field(default_factory=dict)
#     total_score: float = 0.0


@dataclass
class ReviewerInterventionScore:
    reviewer_id: str
    reviewer_email: Optional[str]
    reviewer_username: Optional[str]
    intervention_id: str
    intervention_name: str
    weighted_criteria: dict[str, float] = field(default_factory=dict)  
    total_score: float = 0.0


@dataclass
class ReviewerRanking:
    """
    Individual ranking for one reviewer across interventions they scored.
    Sorted by total_score descending; rank 1 = highest score.
    """
    reviewer_id: str
    reviewer_email: Optional[str]
    reviewer_username: Optional[str]
    ranked_interventions: list[ReviewerInterventionRank] = field(default_factory=list)


@dataclass
class ReviewerInterventionRank:
    rank: int
    intervention_id: str
    intervention_name: str
    total_score: float


@dataclass
class InterventionAggregateScore:
    """
    Aggregate for one intervention across all reviewers who scored it:
      averaged_criteria[c] = mean of (raw_score * individual_weight) across reviewers
                             who actually scored that criteria for this intervention
      average_value_score  = mean of total_weighted_score across reviewers
      reviewer_count       = number of distinct reviewers who scored this intervention
    """
    intervention_id: str
    intervention_name: str
    reviewer_count: int = 0
    averaged_criteria: dict[str, float] = field(default_factory=dict)
    average_value_score: float = 0.0


@dataclass
class AggregateRankingEntry:
    """
    One row in the final aggregate ranking, sorted by average_value_score desc.
    """
    rank: int
    intervention_id: str
    intervention_name: str
    reviewer_count: int
    value: float

# ── Top-level report ──────────────────────────────────────────────────────────
@dataclass
class WeightingReport:
    success: bool
    message: str

    reviewer_results: list[ReviewerWeightingResult] = field(default_factory=list)
    reviewer_scores: list[ReviewerInterventionScore] = field(default_factory=list)
    reviewer_rankings: list[ReviewerRanking] = field(default_factory=list)

    # Full per-intervention aggregate detail (averaged criteria breakdown)
    average_scores: list[InterventionAggregateScore] = field(default_factory=list)

    # Final ranking sorted by average_value_score desc
    average_ranking: list[AggregateRankingEntry] = field(default_factory=list)

    error: Optional[str] = None



# ── Data loading ──────────────────────────────────────────────────────────────

def _load_score_index(
    interventions,
) -> dict[str, dict[str, dict[str, int]]]:
    """
    Returns:
        { reviewer_id (UUID str): { intervention_id: { criteria_name: score_value } } }

    Only interventions where the reviewer actually provided a non-zero score are
    included. Interventions with no scores from a reviewer are simply absent from
    that reviewer's dict — they are never stored as all-None rows.
    """
    index: dict[str, dict[str, dict[str, int]]] = {}

    qs = (
        InterventionScore.objects
        .select_related("criteria")
        .filter(intervention__in=interventions)
    )

    for s in qs:
        value = int(
            s.score.get("score_value", 0)
            if isinstance(s.score, dict)
            else s.score or 0
        )
        if not value:
            continue

        r_id  = str(s.reviewer_id)
        iv_id = str(s.intervention_id)
        cname = s.criteria.criteria.strip()

        index.setdefault(r_id, {}).setdefault(iv_id, {})[cname] = value

    return index


# ── CRITIC helpers (per reviewer) ─────────────────────────────────────────────

def _build_anchors(
    reviewer_scores: dict[str, dict[str, int]],
    criteria_names: list[str],
) -> list[CriteriaAnchor]:
    """
    worst = min score this reviewer gave across their scored interventions.
    best  = max score.
    Falls back to SCORE_MIN/SCORE_MAX when all values are identical so the
    normalisation denominator is never zero.
    """
    anchors = []
    for cname in criteria_names:
        values = [
            reviewer_scores[iv_id][cname]
            for iv_id in reviewer_scores
            if cname in reviewer_scores[iv_id]
        ]
        worst = float(min(values)) if values else float(SCORE_MIN)
        best  = float(max(values)) if values else float(SCORE_MAX)
        if worst == best:
            worst, best = float(SCORE_MIN), float(SCORE_MAX)
        anchors.append(CriteriaAnchor(
            criteria_name=cname,
            worst_value=worst,
            best_value=best,
        ))
    return anchors


def _normalise_value(score: int, worst: float, best: float) -> float:
    if best == worst:
        return 0.0
    return round((score - worst) / (best - worst), 4)


def _build_normalisation(
    reviewer_scores: dict[str, dict[str, int]],
    intervention_meta: dict[str, tuple[str, str]],
    criteria_names: list[str],
    anchors: list[CriteriaAnchor],
    scored_intervention_ids: list[str],   # only interventions this reviewer scored
) -> list[InterventionNormalised]:
    """
    Builds a normalisation report for the interventions this reviewer actually
    scored. Interventions they never touched are excluded entirely.
    For a given intervention, a criteria the reviewer did not score gets
    normalised_value=None (reviewer scored the intervention but missed a criteria).
    """
    anchor_map = {a.criteria_name: a for a in anchors}
    rows = []
    for iv_id in scored_intervention_ids:
        _ref, iv_name = intervention_meta[iv_id]
        iv_scores = reviewer_scores.get(iv_id, {})
        normalised = []
        for cname in criteria_names:
            anchor = anchor_map[cname]
            if cname in iv_scores:
                val: Optional[float] = _normalise_value(
                    iv_scores[cname], anchor.worst_value, anchor.best_value
                )
            else:
                val = None
            normalised.append(NormalisedScore(criteria_name=cname, normalised_value=val))
        rows.append(InterventionNormalised(
            intervention_id=iv_id,
            intervention_name=iv_name,
            normalised=normalised,
        ))
    return rows


def _build_std_devs(
    normalisation_report: list[InterventionNormalised],
    criteria_names: list[str],
) -> list[CriteriaStdDev]:
    """Population SD (sigma) per criteria, skipping None (unscored) cells."""
    std_devs = []
    for cname in criteria_names:
        values = [
            ns.normalised_value
            for iv in normalisation_report
            for ns in iv.normalised
            if ns.criteria_name == cname and ns.normalised_value is not None
        ]
        std_dev = round(float(np.std(values)), 9) if len(values) >= 2 else 0.0
        std_devs.append(CriteriaStdDev(criteria_name=cname, std_dev=std_dev))
    return std_devs


def _extract_normalised_matrix(
    normalisation_report: list[InterventionNormalised],
    criteria_names: list[str],
) -> np.ndarray:
    """Shape (n_scored_interventions, n_criteria). None → 0.0."""
    rows = []
    for iv in normalisation_report:
        score_map = {ns.criteria_name: (ns.normalised_value or 0.0) for ns in iv.normalised}
        rows.append([score_map.get(c, 0.0) for c in criteria_names])
    return np.array(rows, dtype=float)


def _build_pearson_matrix(
    normalisation_report: list[InterventionNormalised],
    criteria_names: list[str],
) -> list[PearsonRow]:
    data = _extract_normalised_matrix(normalisation_report, criteria_names)
    corr = np.nan_to_num(np.corrcoef(data.T), nan=0.0)
    return [
        PearsonRow(
            criteria_name=row_name,
            correlations=[
                PearsonCell(
                    criteria_name=col_name,
                    coefficient=round(float(corr[i, j]), 4),
                )
                for j, col_name in enumerate(criteria_names)
            ],
        )
        for i, row_name in enumerate(criteria_names)
    ]


def _build_conflict_matrix(pearson_matrix: list[PearsonRow]) -> list[ConflictRow]:
    """conflict_ij = 1 - r_ij; sum_of_conflict = row total."""
    return [
        ConflictRow(
            criteria_name=pr.criteria_name,
            conflicts=[
                ConflictCell(
                    criteria_name=cell.criteria_name,
                    conflict_value=round(1.0 - cell.coefficient, 4),
                )
                for cell in pr.correlations
            ],
            sum_of_conflict=round(
                sum(1.0 - cell.coefficient for cell in pr.correlations), 4
            ),
        )
        for pr in pearson_matrix
    ]


def _build_weightings(
    standard_deviations: list[CriteriaStdDev],
    conflict_rows: list[ConflictRow],
) -> list[CriteriaWeighting]:
    """
    For each criteria:
        product         = sd * sum_of_conflict

    Across ALL criteria for this reviewer:
        sum_of_products = sum(all products)
        weight          = product / sum_of_products
        weight_%        = weight * 100
    """
    conflict_map = {cr.criteria_name: cr.sum_of_conflict for cr in conflict_rows}

    entries = []
    for sd in standard_deviations:
        sigma   = round(sd.std_dev, 4)
        soc     = round(conflict_map.get(sd.criteria_name, 0.0), 4)
        product = round(sigma * soc, 4)
        entries.append((sd.criteria_name, sigma, soc, product))

    sum_of_products = round(sum(e[3] for e in entries), 4)

    return [
        CriteriaWeighting(
            criteria_name     = name,
            std_dev           = sigma,
            sum_of_conflict   = soc,
            product           = product,
            sum_of_products   = sum_of_products,
            weight            = round(product / sum_of_products, 4) if sum_of_products else 0.0,
            weight_percentage = round((product / sum_of_products) * 100, 4) if sum_of_products else 0.0,
        )
        for name, sigma, soc, product in entries
    ]


def _run_critic_for_reviewer(
    reviewer_id: str,
    reviewer_scores: dict[str, dict[str, int]],
    intervention_meta: dict[str, tuple[str, str]],
    criteria_names: list[str],
) -> ReviewerWeightingResult:
    """
    Runs the full CRITIC pipeline for a single reviewer.

    Only the interventions this reviewer actually scored are used throughout —
    all-null interventions never enter the pipeline.
    """
    try:
        user = User.objects.get(id=reviewer_id)
        reviewer_email    = user.email
        reviewer_username = user.username
    except User.DoesNotExist:
        reviewer_email    = None
        reviewer_username = None

    # Only interventions this reviewer scored (score_index guarantees non-empty)
    scored_intervention_ids = list(reviewer_scores.keys())

    anchors              = _build_anchors(reviewer_scores, criteria_names)
    normalisation_report = _build_normalisation(
        reviewer_scores, intervention_meta, criteria_names, anchors,
        scored_intervention_ids,
    )
    standard_deviations  = _build_std_devs(normalisation_report, criteria_names)
    pearson_matrix       = _build_pearson_matrix(normalisation_report, criteria_names)
    conflict_matrix      = _build_conflict_matrix(pearson_matrix)
    weightings           = _build_weightings(standard_deviations, conflict_matrix)

    return ReviewerWeightingResult(
        reviewer_id          = reviewer_id,
        reviewer_email       = reviewer_email,
        reviewer_username    = reviewer_username,
        anchors              = anchors,
        normalisation_report = normalisation_report,
        standard_deviations  = standard_deviations,
        pearson_matrix       = pearson_matrix,
        conflict_matrix      = conflict_matrix,
        weightings           = weightings,
    )


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _build_reviewer_scores(
    reviewer_results: list[ReviewerWeightingResult],
    score_index: dict[str, dict[str, dict[str, int]]],
    intervention_meta: dict[str, tuple[str, str]],
    criteria_names: list[str],
) -> list[ReviewerInterventionScore]:
    """
    For each reviewer, for each intervention they scored:
        weighted_score[c] = raw_score[c] * weight[c]   (from that reviewer's CRITIC)
        total_score       = sum of weighted_scores

    Interventions the reviewer never scored are skipped entirely (no null rows).
    """
    rows: list[ReviewerInterventionScore] = []

    for rr in reviewer_results:
        weight_map        = {cw.criteria_name: cw.weight for cw in rr.weightings}
        reviewer_iv_scores = score_index.get(rr.reviewer_id, {})

        for iv_id, iv_scores in reviewer_iv_scores.items():
            _ref, iv_name = intervention_meta[iv_id]

            criteria_scores: list[CriteriaWeightedScore] = []
            for cname in criteria_names:
                raw = iv_scores.get(cname)
                if raw is None:
                    # This reviewer didn't score this criteria for this intervention
                    continue
                w  = weight_map.get(cname, 0.0)
                ws = round(raw * w, 4)
                criteria_scores.append(CriteriaWeightedScore(
                    criteria_name  = cname,
                    raw_score      = raw,
                    weight         = w,
                    weighted_score = ws,
                ))

            total = round(sum(cs.weighted_score for cs in criteria_scores), 4)

            weighted_criteria = {
                cs.criteria_name: cs.weighted_score
                for cs in criteria_scores
            }

            rows.append(ReviewerInterventionScore(
                reviewer_id       = rr.reviewer_id,
                reviewer_email    = rr.reviewer_email,
                reviewer_username = rr.reviewer_username,
                intervention_id   = iv_id,
                intervention_name = iv_name,
                weighted_criteria = weighted_criteria,  # ← correct field
                total_score       = total,
            ))

    return rows


def _build_reviewer_rankings(
    reviewer_score_rows: list[ReviewerInterventionScore],
) -> list[ReviewerRanking]:
    """
    For each reviewer, rank their scored interventions by total_score descending.
    Returns one ReviewerRanking per reviewer.
    """
    # Group rows by reviewer
    by_reviewer: dict[str, list[ReviewerInterventionScore]] = {}
    for row in reviewer_score_rows:
        by_reviewer.setdefault(row.reviewer_id, []).append(row)

    rankings: list[ReviewerRanking] = []
    for reviewer_id, rows in by_reviewer.items():
        sorted_rows = sorted(rows, key=lambda r: r.total_score, reverse=True)
        ranked = [
            ReviewerInterventionRank(
                rank              = idx + 1,
                intervention_id   = r.intervention_id,
                intervention_name = r.intervention_name,
                total_score       = r.total_score,
            )
            for idx, r in enumerate(sorted_rows)
        ]
        rankings.append(ReviewerRanking(
            reviewer_id       = reviewer_id,
            reviewer_email    = rows[0].reviewer_email,
            reviewer_username = rows[0].reviewer_username,
            ranked_interventions = ranked,
        ))

    return rankings



def _build_average_scores(
    reviewer_score_rows: list[ReviewerInterventionScore],
    intervention_meta: dict[str, tuple[str, str]],
    criteria_names: list[str],
) -> tuple[list[InterventionAggregateScore], list[AggregateRankingEntry]]:
    """
    Group by intervention:

      averaged_criteria[c]  = mean of (raw_score * weight) across reviewers who
                               scored that criteria for this intervention
      average_value_score   = mean of each reviewer's total_weighted_score
                               (average of the row totals — not sum of averaged_criteria)
      reviewer_count        = distinct reviewers who scored this intervention

    Returns both the full detail list and the sorted ranking list.
    """
    # { iv_id: { criteria_name: [weighted_value, ...] } }
    criteria_accum: dict[str, dict[str, list[float]]] = {}
    # { iv_id: [total_weighted_score per reviewer, ...] }
    totals_accum: dict[str, list[float]] = {}

    for row in reviewer_score_rows:
        iv_bucket = criteria_accum.setdefault(row.intervention_id, {})
        for cname, wval in row.weighted_criteria.items():
            iv_bucket.setdefault(cname, []).append(wval)

        totals_accum.setdefault(row.intervention_id, []).append(row.total_score)

    average_scores: list[InterventionAggregateScore] = []
    for iv_id, criteria_lists in criteria_accum.items():
        _ref, iv_name = intervention_meta[iv_id]
        reviewer_totals = totals_accum.get(iv_id, [])
        reviewer_count = len(reviewer_totals)

        averaged_criteria: dict[str, float] = {}
        for cname in criteria_names:
            vals = criteria_lists.get(cname, [])
            averaged_criteria[cname] = round(sum(vals) / len(vals), 4) if vals else 0.0

        average_value_score = round(sum(reviewer_totals) / reviewer_count, 4) if reviewer_count else 0.0

        average_scores.append(InterventionAggregateScore(
            intervention_id     = iv_id,
            intervention_name   = iv_name,
            reviewer_count      = reviewer_count,
            averaged_criteria   = averaged_criteria,
            average_value_score = average_value_score,
        ))

    # Sort by average_value_score descending and build ranking
    average_scores.sort(key=lambda x: x.average_value_score, reverse=True)

    average_ranking: list[AggregateRankingEntry] = [
        AggregateRankingEntry(
            rank              = rank_pos,
            intervention_id   = entry.intervention_id,
            intervention_name = entry.intervention_name,
            reviewer_count    = entry.reviewer_count,
            value             = entry.average_value_score,
        )
        for rank_pos, entry in enumerate(average_scores, start=1)
    ]

    return average_scores, average_ranking

# ── Main service ──────────────────────────────────────────────────────────────

class WeightingReportService:

    @staticmethod
    def generate(intervention_ids: list[str] | None = None) -> WeightingReport:
        try:
            qs = InterventionProposal.objects.order_by("reference_number")
            if intervention_ids:
                qs = qs.filter(id__in=intervention_ids)
            interventions = list(qs)

            criteria_names: list[str] = list(
                SelectionTool.objects.values_list("criteria", flat=True)
                .distinct().order_by("criteria")
            )

            # { reviewer_id: { intervention_id: { criteria_name: score } } }
            # Only non-zero, actually-scored entries are present.
            score_index = _load_score_index(interventions)

            if not score_index:
                return WeightingReport(
                    success=False,
                    message="No scores found for the selected interventions.",
                )

            intervention_meta: dict[str, tuple[str, str]] = {
                str(iv.id): (
                    getattr(iv, "reference_number", str(iv.id)),
                    getattr(iv, "intervention_name", str(iv)),
                )
                for iv in interventions
            }

            # ── 1. CRITIC — per reviewer, using only interventions they scored ─
            reviewer_results: list[ReviewerWeightingResult] = [
                _run_critic_for_reviewer(
                    reviewer_id       = reviewer_id,
                    reviewer_scores   = reviewer_scores,
                    intervention_meta = intervention_meta,
                    criteria_names    = criteria_names,
                )
                for reviewer_id, reviewer_scores in score_index.items()
            ]

            # ── 2. Reviewer scores — raw_score * individual CRITIC weight ──────
            reviewer_score_rows = _build_reviewer_scores(
                reviewer_results  = reviewer_results,
                score_index       = score_index,
                intervention_meta = intervention_meta,
                criteria_names    = criteria_names,
            )

            # ── 3. Individual rankings — per reviewer, by total_score ──────────
            reviewer_rankings = _build_reviewer_rankings(reviewer_score_rows)


            average_scores, average_ranking = _build_average_scores(
                reviewer_score_rows = reviewer_score_rows,
                intervention_meta   = intervention_meta,
                criteria_names      = criteria_names,
            )

            return WeightingReport(
                success            = True,
                message            = "OK",
                reviewer_results   = reviewer_results,
                reviewer_scores    = reviewer_score_rows,
                reviewer_rankings  = reviewer_rankings,
                average_scores   = average_scores,
                average_ranking  = average_ranking,
            )
     

        except Exception as exc:
            logger.exception("WeightingReportService.generate failed")
            return WeightingReport(success=False, message="Failed.", error=str(exc))