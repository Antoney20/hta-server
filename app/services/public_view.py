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
            .filter()
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



from app.serializers import PublicProgramProposalSerializer, PublicProgramSerializer
from app.models import NationalProgram, NationalProgramProposal


PROGRAM_PROPOSALS_CACHE_KEY = "public:program-proposals:v1"
PROGRAMS_CACHE_KEY = "public:programs:v1"


class PublicProgramService:
    """
    Public read-only access to national programs and their proposals.

    Responsibilities:
    - optimized querying
    - serialization
    - response payload construction
    - caching
    """

    @staticmethod
    def _proposal_query():
        return (
            NationalProgramProposal.objects
            .select_related("program")
            .only(
                "id",
                "reference_number",
                "title",
                "justification",
                "data",
                "submitted_date",
                "program__id",
                "program__name",
                "program__code",
            )
            .order_by("-submitted_date", "-created_at")
        )

    @staticmethod
    def _program_query():
        return (
            NationalProgram.objects
            .filter(is_active=True)
            .only("id", "name", "code", "description", "field_schema")
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
    def fetch_proposals(cls):
        """
        Cached list of national program proposals.
        """
        cached = cache.get(PROGRAM_PROPOSALS_CACHE_KEY)
        if cached is not None:
            return cached

        queryset = cls._proposal_query()

        serializer = PublicProgramProposalSerializer(queryset, many=True)

        payload = cls._build_payload(serializer.data)

        cache.set(PROGRAM_PROPOSALS_CACHE_KEY, payload, CACHE_TIMEOUT)

        return payload

    @classmethod
    def fetch_programs(cls):
        """
        Cached list of active national programs (with field_schema).
        """
        cached = cache.get(PROGRAMS_CACHE_KEY)
        if cached is not None:
            return cached

        queryset = cls._program_query()

        serializer = PublicProgramSerializer(queryset, many=True)

        payload = cls._build_payload(serializer.data)

        cache.set(PROGRAMS_CACHE_KEY, payload, CACHE_TIMEOUT)

        return payload

    @staticmethod
    def invalidate():
        """Delete caches immediately"""
        cache.delete(PROGRAM_PROPOSALS_CACHE_KEY)
        cache.delete(PROGRAMS_CACHE_KEY)

    @classmethod
    def refresh(cls):
        """Force rebuild caches"""
        cls.invalidate()
        return cls.fetch_proposals(), cls.fetch_programs()