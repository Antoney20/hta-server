from django.core.cache import cache
from django.utils.timezone import now

from app.serializers import PublicProposalSerializer
from users.models import InterventionProposal


CACHE_KEY = "public:proposals:v1"
CACHE_TIMEOUT = 60 * 30  # 30 minutes


class PublicProposalService:
    """

    Responsibilities:
    - optimized querying
    - serialization
    - response payload construction
    - caching
    """


    @staticmethod
    def _query():
        return (
            InterventionProposal.objects
            .filter(is_public=True)
            .only(
                "id",
                "reference_number",
                "intervention_name",
                "intervention_type",
                "beneficiary",
                "justification",
                "expected_impact",
                "additional_info",
                "submitted_at",
            )
            .order_by("-submitted_at")
        )


    @staticmethod
    def _build_payload(data):
        """
        Standard public API response.
        """
        return {
            "status": "success",
            "count": len(data),
            "generated_at": now().isoformat(),
            "results": data,
        }

    @classmethod
    def fetch(cls):
        """
        Main entrypoint (cached).
        """

        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        queryset = cls._query()

        serializer = PublicProposalSerializer(queryset, many=True)

        payload = cls._build_payload(serializer.data)

        cache.set(CACHE_KEY, payload, CACHE_TIMEOUT)

        return payload


    @staticmethod
    def invalidate():
        """Delete cache immediately"""
        cache.delete(CACHE_KEY)

    @classmethod
    def refresh(cls):
        """Force rebuild cache"""
        cls.invalidate()
        return cls.fetch()