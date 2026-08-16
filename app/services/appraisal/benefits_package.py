
from app.models import BenefitPackage, EvidenceExtraction, ProposedBenefitPackage, RevisedBenefitPackage, SwgPrioritizedList
from app.services.appraisal_panel import _get_or_404


def bp_ok(data=None, message="", status=200):
    return {"ok": True, "data": data, "message": message, "status": status}

def bp_err(error, status=400):
    return {"ok": False, "error": error, "status": status}

class SwgListService:
    @staticmethod
    def list(params):
        qs = SwgPrioritizedList.objects.all()
        cycle = (params or {}).get("cycle")
        if cycle:
            qs = qs.filter(cycle=cycle)
        return bp_ok([{"id": str(s.id), "name": s.name, "cycle": s.cycle,
                     "count": len(s.items or [])} for s in qs])

    @staticmethod
    def get(pk):
        s = _get_or_404(SwgPrioritizedList, pk)
        if not s:
            return bp_err("SWG list not found", 404)
        return bp_ok({"id": str(s.id), "name": s.name, "cycle": s.cycle,
                    "data": s.data or {}, "items": s.items or []})

    @staticmethod
    def create(data):
        s = SwgPrioritizedList.objects.create(
            name=data.get("name", ""), cycle=data.get("cycle", ""),
            data=data.get("data", {}) or {}, items=data.get("items", []) or [])
        return bp_ok({"id": str(s.id)}, "Created")

    @staticmethod
    def update(pk, data, partial):
        s = _get_or_404(SwgPrioritizedList, pk)
        if not s:
            return bp_err("SWG list not found", 404)
        for f in ("name", "cycle", "data", "items"):
            if f in data:
                setattr(s, f, data[f])
        s.save()
        return bp_ok({"id": str(s.id)}, "Updated")

    @staticmethod
    def delete(pk):
        s = _get_or_404(SwgPrioritizedList, pk)
        if not s:
            return bp_err("SWG list not found", 404)
        s.delete()
        return bp_ok(None, "Deleted")