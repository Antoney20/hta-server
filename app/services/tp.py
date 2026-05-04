from django.core.cache import cache
from django.db.models import (
    BooleanField, Count, ExpressionWrapper,
    IntegerField, OuterRef, Prefetch, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce
from django.utils.timezone import now

from app.models import (
    DecisionType, InterventionProposal, InterventionScore,
    InterventionStatusUpdate, InterventionSystemCategory,
)
from app.serializers import InterventionStatusUpdateSerializer

CACHE_KEY = "public:topic-priority:v1"
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
    - Unified querying of InterventionStatusUpdate rows + scored-only interventions
    - Serialization and cache management
    - move_to_panel for single and bulk operations
      (auto-creates a minimal status update for scored-only rows)

    Response shape:
    - All InterventionStatusUpdate records (with decision/status)
    - All interventions with >1 score that have no status update yet (id=null rows)
    - is_scored: always bool, never null
    - move_to_panel: always bool
    - decision: always set — 'Pending' sentinel for rows without a formal decision
    """

    # ------------------------------------------------------------------ #
    #  Internal query helpers                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _score_count_subquery():
        return (
            InterventionScore.objects
            .filter(intervention=OuterRef("intervention_id"))
            .values("intervention")
            .annotate(cnt=Count("id"))
            .values("cnt")[:1]
        )

    @classmethod
    def _status_update_queryset(cls):
        """
        All InterventionStatusUpdate rows annotated with is_scored.
        is_scored = True when the intervention has >1 score.
        """
        return (
            InterventionStatusUpdate.objects
            .select_related("intervention", "decision")
            .prefetch_related(
                Prefetch(
                    "intervention__system_categories",
                    queryset=InterventionSystemCategory.objects.select_related(
                        "system_category"
                    ),
                )
            )
            .annotate(
                score_count=Coalesce(
                    Subquery(
                        cls._score_count_subquery(),
                        output_field=IntegerField(),
                    ),
                    Value(0),
                    output_field=IntegerField(),
                ),
                is_scored=ExpressionWrapper(
                    Q(score_count__gt=1),
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
        interventions_with_status = InterventionStatusUpdate.objects.values_list(
            "intervention_id", flat=True
        )
        return (
            InterventionProposal.objects
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

    # ------------------------------------------------------------------ #
    #  Payload assembly                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_payload(status_data, scored_only_interventions) -> dict:
        """
        Merges serialized status update rows with scored-only intervention dicts.
        Status update rows come first (they carry formal decision data).
        """
        pending = TopicPriorityService._get_pending_decision_data()

        scored_only = [
            {
                "id": None,
                "reference_number": i.reference_number,
                "intervention_id": str(i.id),
                "intervention_name": i.intervention_name,
                "decision": pending,
                "decision_date": None,
                "feedback": "",
                "system_categories": [
                    sc.system_category.name
                    for sc in i.system_categories.all()
                ],
                "is_scored": True,
                "move_to_panel": False,
                "created_at": None,
                "updated_at": None,
            }
            for i in scored_only_interventions
        ]

        results = list(status_data) + scored_only

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

        payload = cls._build_payload(serialized, scored_only)
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
    #  Move to panel                                                       #
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
        # Validate all IDs exist
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