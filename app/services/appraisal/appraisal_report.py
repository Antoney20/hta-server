from app.models import (
    BenefitPackage, EvidenceExtraction, PanelAppraisedList,
    ProposedBenefitPackage, RevisedBenefitPackage, SwgPrioritizedList,
)
from app.services.appraisal.benefits_package import bp_err, bp_ok
from app.services.appraisal_panel import _get_or_404

class AppraisedListService:
    @staticmethod
    def list(params):
        qs = PanelAppraisedList.objects.all()
        return bp_ok([{"id": str(a.id), "name": a.name,
                     "count": len(a.items or [])} for a in qs])

    @staticmethod
    def get(pk):
        a = _get_or_404(PanelAppraisedList, pk)
        if not a:
            return bp_err("Appraised list not found", 404)
        return bp_ok({"id": str(a.id), "name": a.name,
                    "data": a.data or {}, "items": a.items or []})

    @staticmethod
    def create(data):
        a = PanelAppraisedList.objects.create(
            name=data.get("name", ""),
            data=data.get("data", {}) or {}, items=data.get("items", []) or [])
        return bp_ok({"id": str(a.id)}, "Created")

    @staticmethod
    def update(pk, data, partial):
        a = _get_or_404(PanelAppraisedList, pk)
        if not a:
            return bp_err("Appraised list not found", 404)
        for f in ("name", "data", "items"):
            if f in data:
                setattr(a, f, data[f])
        a.save()
        return bp_ok({"id": str(a.id)}, "Updated")

    @staticmethod
    def delete(pk):
        a = _get_or_404(PanelAppraisedList, pk)
        if not a:
            return bp_err("Appraised list not found", 404)
        a.delete()
        return bp_ok(None, "Deleted")