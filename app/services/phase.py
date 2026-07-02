from app.models import InterventionPhase, NationalProgramProposal
from users.models import InterventionProposal


class InterventionPhaseService:

    @staticmethod
    def list_phases():
        return InterventionPhase.objects.all()

    @staticmethod
    def create_phase(data):
        return InterventionPhase.objects.create(**data)

    @staticmethod
    def update_phase(phase, data):
        for field, value in data.items():
            setattr(phase, field, value)
        phase.save()
        return phase

    @staticmethod
    def delete_phase(phase):
        phase.delete()

    @staticmethod
    def link_one(phase, ref):
        proposal = (
            InterventionProposal.objects.filter(reference_number=ref).first()
            or NationalProgramProposal.objects.filter(reference_number=ref).first()
        )
        if not proposal:
            return False
        proposal.phase = phase
        proposal.save(update_fields=["phase"])
        return True

    @staticmethod
    def bulk_upload(rows):
        results = {"attached": [], "errors": []}
        for i, row in enumerate(rows):
            name = (row.get("name") or "").strip()
            ref = (row.get("reference_number") or "").strip()
            if not name or not ref:
                results["errors"].append({"row": i, "ref": ref, "error": "Missing name or reference_number"})
                continue
            phase = InterventionPhase.objects.filter(name__iexact=name).first()
            if phase is None:
                results["errors"].append({"row": i, "ref": ref, "error": f"Phase '{name}' not found"})
                continue
            proposal = (
                InterventionProposal.objects.filter(reference_number=ref).first()
                or NationalProgramProposal.objects.filter(reference_number=ref).first()
            )
            if not proposal:
                results["errors"].append({"row": i, "ref": ref, "error": "No proposal found for reference"})
                continue
            proposal.phase = phase
            proposal.save(update_fields=["phase"])
            results["attached"].append({"row": i, "ref": ref, "phase": phase.name})
        return results

    @staticmethod
    def grouped():
        out = []
        qs = InterventionPhase.objects.prefetch_related("interventions", "national_proposals")
        for phase in qs:
            members = [
                {
                    "kind": "intervention",
                    "id": str(i.id),
                    "reference_number": i.reference_number,
                    "name": getattr(i, "intervention_name", None),
                }
                for i in phase.interventions.all()
            ] + [
                {
                    "kind": "program",
                    "id": str(p.id),
                    "reference_number": p.reference_number,
                    "name": p.title,
                }
                for p in phase.national_proposals.all()
            ]
            out.append({
                "id": phase.id,
                "name": phase.name,
                "description": phase.description,
                "order": phase.order,
                "is_active": phase.is_active,
                "members": members,
            })
        return out