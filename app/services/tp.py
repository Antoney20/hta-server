from django.core.cache import cache
from django.db.models import (
    BooleanField, Count, ExpressionWrapper, F,
    IntegerField, OuterRef, Prefetch, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce
from django.utils.timezone import now

from app.models import (
    DecisionType, InterventionProposal, InterventionScore,
    InterventionStatusUpdate, InterventionSystemCategory, NationalProgramProposal,
)
from app.serializers import InterventionStatusUpdateSerializer

CACHE_KEY = "public:topic-priority:v2"
CACHE_TIMEOUT = 60 * 30  # 30 minutes

PENDING_DECISION_NAME = "Pending"


def get_pending_decision_id():
    """
    Returns the PK of the 'Pending' DecisionType sentinel, creating it if needed.
    Used as the FK default on InterventionStatusUpdate.decision.
    """
    obj, _ = DecisionType.objects.get_or_create(
        name=PENDING_DECISION_NAME,
        defaults={"description": "Awaiting formal HTA decision."},
    )
    return obj.id


class TopicPriorityService:
    """
    Responsibilities:
    - Unified querying of InterventionStatusUpdate rows (intervention OR national
      proposal targets) + scored-only interventions
    - Serialization and cache management
    - move_to_panel for single and bulk operations
      (auto-creates a minimal status update for scored-only rows)

    Response shape (each result row):
    - Status update rows (with decision/status), for either target type
    - Interventions with >1 score and no status update yet (id=null rows)
    - National proposals with >1 score and no status update yet (id=null rows)
    - is_scored: always bool, never null — true for either target type once it has
      more than one InterventionScore row
    - move_to_panel: always bool
    - decision: always set — 'Pending' sentinel for rows without a formal decision

    InterventionScore carries nullable FKs to BOTH InterventionProposal and
    NationalProgramProposal, so scoring is judged per target type and summed.
    """

    @staticmethod
    def _score_count_subquery():
        return (
            InterventionScore.objects
            .filter(intervention=OuterRef("intervention_id"))
            .values("intervention")
            .annotate(cnt=Count("id"))
            .values("cnt")[:1]
        )

    @staticmethod
    def _national_score_count_subquery():
        return (
            InterventionScore.objects
            .filter(national_proposal=OuterRef("national_proposal_id"))
            .values("national_proposal")
            .annotate(cnt=Count("id"))
            .values("cnt")[:1]
        )

    @classmethod
    def _status_update_queryset(cls):
        """
        All InterventionStatusUpdate rows (both target types) annotated with
        is_scored. Rows are XOR: an intervention row has national_proposal_id null
        (national subquery matches nothing → 0) and a national row has
        intervention_id null (intervention subquery matches nothing → 0), so the two
        counts never overlap and summing them is safe. is_scored fires when EITHER
        target has more than one score.
        """
        return (
            InterventionStatusUpdate.objects
            .select_related(
                "intervention", "decision",
                "intervention__package", "intervention__phase",
                "national_proposal",
                "national_proposal__package", "national_proposal__phase",
            )
            .prefetch_related(
                Prefetch(
                    "intervention__system_categories",
                    queryset=InterventionSystemCategory.objects.select_related(
                        "system_category"
                    ),
                )
            )
            .annotate(
                _int_score_count=Coalesce(
                    Subquery(
                        cls._score_count_subquery(),
                        output_field=IntegerField(),
                    ),
                    Value(0),
                    output_field=IntegerField(),
                ),
                _nat_score_count=Coalesce(
                    Subquery(
                        cls._national_score_count_subquery(),
                        output_field=IntegerField(),
                    ),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            .annotate(
                score_count=F("_int_score_count") + F("_nat_score_count"),
                is_scored=ExpressionWrapper(
                    Q(_int_score_count__gt=1) | Q(_nat_score_count__gt=1),
                    output_field=BooleanField(),
                ),
            )
            .order_by("-created_at")
        )

    @staticmethod
    def _scored_interventions_without_status():
        """
        Interventions with >1 score that have NO InterventionStatusUpdate row at all.
        These surface as id=null / Pending rows in the response.
        """
        interventions_with_status = (
            InterventionStatusUpdate.objects
            .filter(intervention__isnull=False)
            .values_list("intervention_id", flat=True)
        )
        return (
            InterventionProposal.objects
            .select_related("package", "phase")
            .annotate(score_count=Count("scores"))
            .filter(score_count__gt=1)
            .exclude(id__in=interventions_with_status)
            .prefetch_related(
                Prefetch(
                    "system_categories",
                    queryset=InterventionSystemCategory.objects.select_related(
                        "system_category"
                    ),
                )
            )
            .order_by("-score_count")
        )

    @staticmethod
    def _national_proposals_without_status():
        """
        National program proposals with NO InterventionStatusUpdate row yet.
        Surface as id=null / Pending rows so they can be assigned a review status.
        Every proposal with a reference number and no status update is included; the
        real score count is annotated so is_scored is reported correctly per row.
        """
        nationals_with_status = (
            InterventionStatusUpdate.objects
            .filter(national_proposal__isnull=False)
            .values_list("national_proposal_id", flat=True)
        )
        return (
            NationalProgramProposal.objects
            .select_related("package", "phase")
            .filter(reference_number__isnull=False)
            .exclude(id__in=nationals_with_status)
            .annotate(score_count=Count("scores"))
            .order_by("-created_at")
        )

    @staticmethod
    def _get_pending_decision_data() -> dict | None:
        """Single query to get the Pending sentinel for scored-only row payloads."""
        obj = (
            DecisionType.objects
            .filter(name=PENDING_DECISION_NAME)
            .values("id", "name", "description")
            .first()
        )
        if not obj:
            return None
        return {
            "id": str(obj["id"]),
            "name": obj["name"],
            "description": obj["description"],
        }

    @staticmethod
    def _build_payload(status_data, scored_only_interventions, national_only_proposals) -> dict:
        pending = TopicPriorityService._get_pending_decision_data()

        scored_only = [
            {
                "id": None,
                "target_type": "intervention",
                "reference_number": i.reference_number,
                "intervention_id": str(i.id),
                "national_proposal_id": None,
                "intervention_name": i.intervention_name,
                "decision": pending,
                "routing_decision": None,
                "decision_date": None,
                "feedback": "",
                "system_categories": [
                    sc.system_category.name for sc in i.system_categories.all()
                ],
                "package": i.package.name if i.package_id else None,
                "phase": i.phase.name if i.phase_id else None,
                "is_scored": True,
                "move_to_panel": False,
                "created_at": None,
                "updated_at": None,
            }
            for i in scored_only_interventions
        ]

        national_only = [
            {
                "id": None,
                "target_type": "national_proposal",
                "reference_number": n.reference_number,
                "intervention_id": None,
                "national_proposal_id": str(n.id),
                "intervention_name": n.title,   # generic name slot the FE reads
                "decision": pending,
                "routing_decision": None,
                "decision_date": None,
                "feedback": "",
                "system_categories": [],
                "package": n.package.name if n.package_id else None,
                "phase": n.phase.name if n.phase_id else None,
                "is_scored": n.score_count > 1,
                "move_to_panel": False,
                "created_at": None,
                "updated_at": None,
            }
            for n in national_only_proposals
        ]

        results = list(status_data) + scored_only + national_only

        return {
            "status": "success",
            "count": len(results),
            "generated_at": now().isoformat(),
            "results": results,
        }

    # ------------------------------------------------------------------ #
    #  Public read                                                         #
    # ------------------------------------------------------------------ #

    @classmethod
    def fetch(cls) -> dict:
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        status_qs = cls._status_update_queryset()
        serialized = InterventionStatusUpdateSerializer(status_qs, many=True).data

        scored_only = cls._scored_interventions_without_status()
        national_only = cls._national_proposals_without_status()

        payload = cls._build_payload(serialized, scored_only, national_only)
        cache.set(CACHE_KEY, payload, CACHE_TIMEOUT)

        return payload

    # ------------------------------------------------------------------ #
    #  CRUD                                                                #
    # ------------------------------------------------------------------ #

    @classmethod
    def create(cls, validated_data: dict, user) -> InterventionStatusUpdate:
        instance = InterventionStatusUpdate.objects.create(
            **validated_data,
            updated_by=user,
        )
        cls.invalidate()
        return instance

    @classmethod
    def update(
        cls, instance: InterventionStatusUpdate, validated_data: dict, user
    ) -> InterventionStatusUpdate:
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.updated_by = user
        instance.save()
        cls.invalidate()
        return instance

    @classmethod
    def delete(cls, instance: InterventionStatusUpdate) -> None:
        instance.delete()
        cls.invalidate()

    # ------------------------------------------------------------------ #
    #  Move to panel (intervention-only)                                   #
    # ------------------------------------------------------------------ #

    @classmethod
    def move_to_panel(cls, intervention_id: str, user) -> InterventionStatusUpdate:
        """
        Marks a single intervention for panel review.

        If no InterventionStatusUpdate exists yet (scored-only row), a minimal one
        is created with the Pending decision. This is the ONLY place a status update
        is implicitly created.
        """
        intervention = InterventionProposal.objects.get(id=intervention_id)

        su, created = InterventionStatusUpdate.objects.get_or_create(
            intervention=intervention,
            defaults={
                "updated_by": user,
                "decision_id": get_pending_decision_id(),
                "move_to_panel": True,
            },
        )

        if not created and not su.move_to_panel:
            su.move_to_panel = True
            su.updated_by = user
            su.save(update_fields=["move_to_panel", "updated_by", "updated_at"])

        cls.invalidate()
        return su

    @classmethod
    def bulk_move_to_panel(cls, intervention_ids: list[str], user) -> dict:
        """
        Moves multiple interventions to panel in two efficient queries.

        - Rows that already have a status update  → single UPDATE
        - Scored-only rows (no status update yet) → bulk_create minimal records
        - Already-moved rows are skipped cleanly (filter move_to_panel=False)

        Raises ValueError if any intervention_id is not found.
        """
        interventions = InterventionProposal.objects.filter(id__in=intervention_ids)
        if interventions.count() != len(intervention_ids):
            found = set(str(i.id) for i in interventions)
            missing = [i for i in intervention_ids if i not in found]
            raise ValueError(f"Interventions not found: {missing}")

        existing_sus = InterventionStatusUpdate.objects.filter(
            intervention_id__in=intervention_ids
        )
        existing_intervention_ids = set(
            str(su.intervention_id) for su in existing_sus
        )

        # 1. Update existing status update rows not already moved
        updated_count = existing_sus.filter(move_to_panel=False).update(
            move_to_panel=True,
            updated_by=user,
        )

        # 2. Bulk-create minimal records for scored-only rows
        needs_create = [
            iid for iid in intervention_ids
            if iid not in existing_intervention_ids
        ]
        if needs_create:
            pending_id = get_pending_decision_id()
            InterventionStatusUpdate.objects.bulk_create([
                InterventionStatusUpdate(
                    intervention_id=iid,
                    move_to_panel=True,
                    updated_by=user,
                    decision_id=pending_id,
                )
                for iid in needs_create
            ])
            updated_count += len(needs_create)

        cls.invalidate()
        return {"updated": updated_count}

    @staticmethod
    def invalidate() -> None:
        cache.delete(CACHE_KEY)

    @classmethod
    def refresh(cls) -> dict:
        cls.invalidate()
        return cls.fetch()