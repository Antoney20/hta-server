from django.core.cache import cache
from django.utils.timezone import now
from django.db.models import Count

from app.models import InterventionStatusUpdate, InterventionScore
from app.serializers import InterventionStatusUpdateSerializer

CACHE_KEY = "public:topic-priority:v1"
CACHE_TIMEOUT = 60 * 30  # 30 minutes


class TopicPriorityService:
    """
    Responsibilities:
    - resolve live ON_REVIEW status from score count
    - optimized querying with select/prefetch
    - serialization and response payload construction
    - caching (public GET only)
    """

    @staticmethod
    def _promote_on_review(queryset):
        """
        If an intervention has >= 2 scores, its effective status is ON_REVIEW
        regardless of the stored value. Annotate and override in Python to avoid
        a write on every fetch.
        """
        scored_ids = set(
            InterventionScore.objects
            .values("intervention_id")
            .annotate(score_count=Count("id"))
            .filter(score_count__gte=2)
            .values_list("intervention_id", flat=True)
        )

        results = []
        for update in queryset:
            if (
                update.status == InterventionStatusUpdate.StatusChoices.PENDING
                and update.intervention_id in scored_ids
            ):
                update.status = "ON_REVIEW"  # transient override, not saved
            results.append(update)
        return results

    @staticmethod
    def _query():
        return (
            InterventionStatusUpdate.objects
            .select_related("intervention", "decision", "updated_by")
            .only(
                "id", "status", "decision", "decision_date",
                "feedback", "created_at", "updated_at",
                "intervention__id",
                "intervention__intervention_name",
                "intervention__reference_number",
            )
            .order_by("-created_at")
        )

    @staticmethod
    def _build_payload(data):
        return {
            "status": "success",
            "count": len(data),
            "generated_at": now().isoformat(),
            "results": data,
        }

    @classmethod
    def fetch(cls):
        """Public entrypoint — cached."""
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        queryset = cls._query()
        promoted = cls._promote_on_review(queryset)
        serializer = InterventionStatusUpdateSerializer(promoted, many=True)
        payload = cls._build_payload(serializer.data)
        cache.set(CACHE_KEY, payload, CACHE_TIMEOUT)
        return payload

    @classmethod
    def create(cls, validated_data, user):
        update = InterventionStatusUpdate.objects.create(
            **validated_data, updated_by=user
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