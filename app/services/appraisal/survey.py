"""
Panel Weighting — deterministic service layer (HTTP-free).

Owns all logic: active-survey resolution, response upsert, validation, and
committee aggregation. Model/deterministic wall: no LLM here. Aggregation is
plain arithmetic and vote tallies over submitted responses only, so every
committee number is reproducible and auditable.
"""

from django.db import transaction
from django.utils import timezone

from app.models import (
    WeightingAllocation,
    WeightingKillerFlag,
    WeightingResponse,
    WeightingSurvey,
)

TOTAL_POINTS = 100


class WeightingService:

    @staticmethod
    def create_survey(user, data):
        return WeightingSurvey.objects.create(
            title=data.get("title", ""),
            description=data.get("description", ""),
            status=data.get("status", "draft"),
            opened_at=data.get("opened_at"),
            closed_at=data.get("closed_at"),
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

    @staticmethod
    def delete_survey(survey):
        survey.delete()  # cascades to responses + children

    DEFAULT_TITLE = "Criteria Weighting Survey"

    @classmethod
    def active_survey(cls):
        """
        The single survey the id-less member endpoints act on. Prefers an OPEN
        survey, else the most recent one; if none exists yet, auto-provisions a
        default OPEN survey so members can always submit.
        """
        survey = (
            WeightingSurvey.objects.filter(status="open").order_by("-created_at", "-id").first()
            or WeightingSurvey.objects.order_by("-created_at", "-id").first()
        )
        if survey is None:
            survey = WeightingSurvey.objects.create(
                title=cls.DEFAULT_TITLE,
                status="open",
                opened_at=timezone.now(),
            )
        return survey

    # ---- create scores (submit one member's response) -------------------
    @staticmethod
    @transaction.atomic
    def submit_response(survey, user, payload):
        """
        Upsert this member's response and its child rows, then mark submitted.
        Returns (response, error). error is None on success.
        respondent_name is taken from request.user (email, then username), not
        from the client. One submission per member; Part A must sum to 100.
        """
        if WeightingResponse.objects.filter(
            survey=survey, respondent=user, submitted_at__isnull=False
        ).exists():
            return None, "You have already submitted your response for this survey."

        allocations = payload.get("allocations") or []
        total = sum(int(a.get("points", 0) or 0) for a in allocations)
        if total != TOTAL_POINTS:
            return None, f"Allocations must sum to exactly {TOTAL_POINTS} (got {total})."

        resp, _ = WeightingResponse.objects.get_or_create(survey=survey, respondent=user)
        resp.respondent_name = (
            getattr(user, "email", "") or getattr(user, "username", "") or ""
        )
        resp.respondent_role = payload.get("respondent_role", "")
        resp.response_date = payload.get("response_date")
        resp.sensitivity_criterion = payload.get("sensitivity_criterion", "")
        resp.scenario_1_choice = payload.get("scenario_1_choice", "")
        resp.scenario_2_choice = payload.get("scenario_2_choice", "")
        resp.submitted_at = timezone.now()
        resp.save()

        # Replace children wholesale (idempotent re-submits).
        resp.allocations.all().delete()
        resp.killer_flags.all().delete()
        WeightingAllocation.objects.bulk_create([
            WeightingAllocation(
                response=resp,
                criterion=a.get("criterion", ""),
                points=int(a.get("points", 0) or 0),
            )
            for a in allocations
        ])
        WeightingKillerFlag.objects.bulk_create([
            WeightingKillerFlag(
                response=resp,
                candidate=k.get("candidate", ""),
                is_killer=bool(k.get("is_killer", False)),
                rank=k.get("rank"),
                other_text=k.get("other_text", ""),
            )
            for k in (payload.get("killer_flags") or [])
        ])
        return resp, None

    # ---- get scores (committee aggregation) -----------------------------
    @staticmethod
    def aggregate(survey):
        """
        Deterministic committee-level roll-up over SUBMITTED responses only.
        Per-criterion mean divides by respondent count (a member who gave a
        criterion 0/nothing still counts), so the means sum back to ~100.
        Also tallies killer votes, sensitivity picks, and trade-off choices.
        """
        responses = list(
            survey.responses.filter(submitted_at__isnull=False)
            .prefetch_related("allocations", "killer_flags")
        )
        n = len(responses)

        points = {}   # criterion -> summed points
        killers = {}  # candidate -> {"votes", "rank_score"}
        sens = {}     # criterion -> count
        s1 = {}       # choice -> count
        s2 = {}       # choice -> count
        resp_rows = []  # per-response scores with respondent name

        for r in responses:
            row_points = {}
            for a in r.allocations.all():
                points[a.criterion] = points.get(a.criterion, 0) + a.points
                row_points[a.criterion] = a.points
            for k in r.killer_flags.all():
                if not (k.is_killer or k.rank):
                    continue
                slot = killers.setdefault(k.candidate, {"votes": 0, "rank_score": 0})
                if k.is_killer:
                    slot["votes"] += 1
                if k.rank in (1, 2, 3):
                    slot["rank_score"] += (4 - k.rank)  # 1->3, 2->2, 3->1
            if r.sensitivity_criterion:
                sens[r.sensitivity_criterion] = sens.get(r.sensitivity_criterion, 0) + 1
            if r.scenario_1_choice:
                s1[r.scenario_1_choice] = s1.get(r.scenario_1_choice, 0) + 1
            if r.scenario_2_choice:
                s2[r.scenario_2_choice] = s2.get(r.scenario_2_choice, 0) + 1
            resp_rows.append({
                "respondent_name": r.respondent_name,
                "points": row_points,
                "sensitivity_criterion": r.sensitivity_criterion,
                "scenario_1_choice": r.scenario_1_choice,
                "scenario_2_choice": r.scenario_2_choice,
            })

        criteria = [
            {"criterion": c, "total_points": pts}
            for c, pts in sorted(points.items(), key=lambda x: -x[1])
        ]
        return {
            "survey_id": survey.id,
            "respondent_count": n,
            "criteria": criteria,
            "responses": resp_rows,
            "killer_criteria": killers,
            "sensitivity": sens,
            "scenario_1": s1,
            "scenario_2": s2,
        }