from app.models import  NationalProgramProposal
from users.models import InterventionProposal


class ProposalLookupService:
    """
    Resolves a proposal of either type by id and returns a normalized,
    target-agnostic detail dict the frontend can render without branching.
    HTTP-free; returns (data, error) style via the caller.
    """

    @staticmethod
    def _intervention_qs():
        return InterventionProposal.objects.select_related("package", "phase")

    @staticmethod
    def _national_qs():
        return (
            NationalProgramProposal.objects
            .select_related("program", "package", "phase")
        )

    @classmethod
    def resolve(cls, pk: str) -> dict | None:
        """
        One id, two possible tables. Intervention first (the common case),
        then national. Returns None if neither matches.
        """
        obj = cls._intervention_qs().filter(pk=pk).first()
        if obj:
            return cls._intervention_payload(obj)

        obj = cls._national_qs().filter(pk=pk).first()
        if obj:
            return cls._national_payload(obj)

        return None

    @staticmethod
    def _intervention_payload(o: InterventionProposal) -> dict:
        return {
            "id": str(o.id),
            "target_type": "intervention",
            "name": o.intervention_name,
            "reference_number": o.reference_number,
            "package": o.package.name if o.package_id else None,
            "phase": o.phase.name if o.phase_id else None,
        }

    @staticmethod
    def _national_payload(o: NationalProgramProposal) -> dict:
        return {
            "id": str(o.id),
            "target_type": "national_proposal",
            "name": o.title,
            "reference_number": o.reference_number,
            "package": o.package.name if o.package_id else None,
            "phase": o.phase.name if o.phase_id else None,
        }