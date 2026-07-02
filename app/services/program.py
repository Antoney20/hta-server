from rest_framework.response import Response   # ← was `from requests import Response`

from app.models import InterventionPackage, NationalProgramProposal
from users.models import InterventionProposal


def _ok(data, message="Success", status_code=200):
    return Response({"success": True, "message": message, "data": data}, status=status_code)


def _err(message, status_code=400):
    return Response({"success": False, "message": message, "data": None}, status=status_code)


def _get_or_404(model, **kwargs):
    """Returns (instance, None) or (None, error Response)."""
    try:
        return model.objects.get(**kwargs), None
    except model.DoesNotExist:
        return None, _err(f"{model.__name__} not found.", 404)


class InterventionPackageService:

    @staticmethod
    def list_packages():
        return InterventionPackage.objects.all().order_by("-created_at")

    @staticmethod
    def create_package(data):
        return InterventionPackage.objects.create(**data)

    @staticmethod
    def update_package(pkg, data):
        for field, value in data.items():
            setattr(pkg, field, value)
        pkg.save()
        return pkg

    @staticmethod
    def delete_package(pkg):
        pkg.delete()


    @staticmethod
    def link_one(pkg, ref):
        proposal = (
            InterventionProposal.objects.filter(reference_number=ref).first()
            or NationalProgramProposal.objects.filter(reference_number=ref).first()
        )
        if not proposal:
            return False
        proposal.package = pkg
        proposal.save(update_fields=["package"])
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

            pkg = InterventionPackage.objects.filter(name__iexact=name).first()
            if pkg is None:
                results["errors"].append({"row": i, "ref": ref, "error": f"Package '{name}' not found"})
                continue

            proposal = (
                InterventionProposal.objects.filter(reference_number=ref).first()
                or NationalProgramProposal.objects.filter(reference_number=ref).first()
            )
            if not proposal:
                results["errors"].append({"row": i, "ref": ref, "error": "No proposal found for reference"})
                continue

            proposal.package = pkg
            proposal.save(update_fields=["package"])
            results["attached"].append({"row": i, "ref": ref, "package": pkg.name})

        return results



    @staticmethod
    def grouped():
        out = []
        qs = InterventionPackage.objects.order_by("name").prefetch_related(
            "interventions", "national_proposals",
        )
        for pkg in qs:
            members = [
                {
                    "kind": "intervention",
                    "id": str(i.id),
                    "reference_number": i.reference_number,
                    "name": getattr(i, "intervention_name", None),
                }
                for i in pkg.interventions.all()
            ] + [
                {
                    "kind": "program",
                    "id": str(p.id),
                    "reference_number": p.reference_number,
                    "name": p.title,
                }
                for p in pkg.national_proposals.all()
            ]
            out.append({
                "id": pkg.id,
                "name": pkg.name,
                "description": pkg.description,
                "field_schema": pkg.field_schema,
                "members": members,
            })
        return out




