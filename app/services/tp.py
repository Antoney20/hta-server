from django.core.cache import cache
from django.db.models import (
    BooleanField, Count, ExpressionWrapper,
    IntegerField, OuterRef, Prefetch, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce
from django.utils.timezone import now

from app.models import (
    InterventionProposal, InterventionScore,
    InterventionStatusUpdate, InterventionSystemCategory,
)
from app.serializers import InterventionStatusUpdateSerializer

CACHE_KEY = "public:topic-priority:v1"
CACHE_TIMEOUT = 60 * 30  # 30 minutes


class TopicPriorityService:
    """
    Responsibilities:
    - optimized querying
    - serialization
    - caching public response

    Response includes:
    - All InterventionStatusUpdate records (with their decision/status)
    - All interventions with >9 scores even if no status update exists
    - is_scored: true/false, never null
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

    @classmethod
    def _status_update_queryset(cls):
        """
        All InterventionStatusUpdate rows, annotated with is_scored.
        is_scored = True if that intervention has >9 scores, else False (never null).
        """
        return (
            InterventionStatusUpdate.objects
            .select_related("intervention", "decision")
            .prefetch_related(
                Prefetch(
                    "intervention__system_categories",
                    queryset=InterventionSystemCategory.objects.select_related("system_category"),
                )
            )
            .annotate(
                score_count=Coalesce(
                    Subquery(cls._score_count_subquery(), output_field=IntegerField()),
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
        Interventions with >9 scores that have NO InterventionStatusUpdate at all.
        Returned as lightweight dicts to merge into the payload.
        """
        interventions_with_status = (
            InterventionStatusUpdate.objects
            .values_list("intervention_id", flat=True)
        )

        return (
            InterventionProposal.objects
            .annotate(score_count=Count("scores"))
            .filter(
                score_count__gt=1,
            )
            .exclude(id__in=interventions_with_status)
            .prefetch_related(
                Prefetch(
                    "system_categories",
                    queryset=InterventionSystemCategory.objects.select_related("system_category"),
                )
            )
            .order_by("-score_count")
        )

    @staticmethod
    def _build_payload(status_data, scored_only_interventions):
        """
        Merge status update records + scored-only interventions.
        Status update records come first (they have a formal decision/status).
        """
        scored_only = [
            {
                "id": None,
                "reference_number": i.reference_number,
                "intervention_id": i.id,
                "intervention_name": i.intervention_name,
                "decision": None,
                "decision_date": None,
                "feedback": "",
                "system_categories": [
                    sc.system_category.name
                    for sc in i.system_categories.all()
                ],
                "is_scored": True,
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

    @classmethod
    def fetch(cls):
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        status_qs = cls._status_update_queryset()
        serialized = InterventionStatusUpdateSerializer(status_qs, many=True).data

        scored_only = cls._scored_interventions_without_status()

        payload = cls._build_payload(serialized, scored_only)
        cache.set(CACHE_KEY, payload, CACHE_TIMEOUT)

        return payload

    @classmethod
    def create(cls, validated_data, user):
        update = InterventionStatusUpdate.objects.create(
            **validated_data,
            updated_by=user,
        )
        cls.invalidate()
        return update

    @classmethod
    def update(cls, instance, validated_data, user):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.updated_by = user
        instance.save()

        cls.invalidate()
        return instance

    @classmethod
    def delete(cls, instance):
        instance.delete()
        cls.invalidate()

    @staticmethod
    def invalidate():
        cache.delete(CACHE_KEY)

    @classmethod
    def refresh(cls):
        cls.invalidate()
        return cls.fetch()
    
    
    