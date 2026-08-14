
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


class ProposedPackageService:
    DECISIONS = {"include", "exclude", "pending"}

    # ---- resolution ---------------------------------------------------------
    @staticmethod
    def _evidence_map(items):
        """proposal_id -> evidence_id. Two batched queries. `kind` picks the FK."""
        interv = [it["id"] for it in items if it.get("id") and it.get("kind") != "national"]
        natl   = [it["id"] for it in items if it.get("id") and it.get("kind") == "national"]
        m = {}
        if interv:
            for eid, pid in EvidenceExtraction.objects.filter(
                    intervention_proposal_id__in=interv).values_list("id", "intervention_proposal_id"):
                m[str(pid)] = str(eid)
        if natl:
            for eid, pid in EvidenceExtraction.objects.filter(
                    national_proposal_id__in=natl).values_list("id", "national_proposal_id"):
                m[str(pid)] = str(eid)
        return m

    @classmethod
    def _grouped(cls, pkg):
        items = pkg.items or []
        ev = cls._evidence_map(items)
        groups = {}
        for it in items:
            row = {
                "id": it.get("id"),
                "ref": it.get("ref", ""),
                "name": it.get("name", ""),
                "kind": it.get("kind", "intervention"),
                "service_type": it.get("service_type", ""),
                "package_access": it.get("package_access", ""),
                "routing": it.get("routing", ""),
                "decision": it.get("decision", "pending"),
                "comment": it.get("comment", ""),
                "evidence_id": ev.get(str(it.get("id"))),
            }
            groups.setdefault(row["service_type"] or "—", []).append(row)
        current = BenefitPackage.objects.filter(name=pkg.name).first()
        return {
            "id": str(pkg.id), "name": pkg.name, "fund": pkg.fund,
            "current": (current.items or []) if current else [],
            "services": [{"service": s, "interventions": v} for s, v in groups.items()],
        }

    # ---- CRUD ---------------------------------------------------------------
    @staticmethod
    def list(params):
        qs = ProposedBenefitPackage.objects.all()
        fund = (params or {}).get("fund")
        if fund:
            qs = qs.filter(fund=fund)
        return bp_ok([{"id": str(p.id), "name": p.name, "fund": p.fund,
                     "count": len(p.items or [])} for p in qs])

    @classmethod
    def get(cls, pk):
        pkg = _get_or_404(ProposedBenefitPackage, pk)
        if not pkg:
            return bp_err("Proposed package not found", 404)
        return bp_ok(cls._grouped(pkg))

    @classmethod
    def overview(cls, params=None):
        qs = ProposedBenefitPackage.objects.all()
        fund = (params or {}).get("fund")
        if fund:
            qs = qs.filter(fund=fund)
        return bp_ok([cls._grouped(p) for p in qs])

    @staticmethod
    def create(data):
        pkg = ProposedBenefitPackage.objects.create(
            name=data.get("name", ""), fund=data.get("fund", ""),
            data=data.get("data", {}) or {}, items=data.get("items", []) or [])
        return bp_ok({"id": str(pkg.id)}, "Created")

    @staticmethod
    def update(pk, data, partial):
        pkg = _get_or_404(ProposedBenefitPackage, pk)
        if not pkg:
            return bp_err("Proposed package not found", 404)
        for f in ("name", "fund", "data", "items"):
            if f in data:
                setattr(pkg, f, data[f])
        pkg.save()
        return bp_ok({"id": str(pkg.id)}, "Updated")

    @staticmethod
    def delete(pk):
        pkg = _get_or_404(ProposedBenefitPackage, pk)
        if not pkg:
            return bp_err("Proposed package not found", 404)
        pkg.delete()
        return bp_ok(None, "Deleted")

    # ---- decision -----------------------------------------------------------
    @classmethod
    def set_decision(cls, pk, payload):
        ref = payload.get("ref")
        decision = (payload.get("decision") or "pending").lower()
        if decision not in cls.DECISIONS:
            return bp_err(f"decision must be one of {sorted(cls.DECISIONS)}", 400)
        pkg = _get_or_404(ProposedBenefitPackage, pk)
        if not pkg:
            return bp_err("Proposed package not found", 404)
        items = pkg.items or []
        hit = next((it for it in items
                    if it.get("ref") == ref or str(it.get("id")) == str(ref)), None)
        if not hit:
            return bp_err("Intervention not in package", 404)
        hit["decision"] = decision
        if "comment" in payload:
            hit["comment"] = payload["comment"]
        pkg.items = items
        pkg.save(update_fields=["items", "updated_at"])
        return bp_ok(hit)

    # ---- bridge: SWG -> grouped proposed packages ---------------------------
    @classmethod
    def build_from_swg(cls, payload):
        swg = _get_or_404(SwgPrioritizedList, payload.get("swg_id"))
        if not swg:
            return bp_err("SWG list not found", 404)
        hta = payload.get("hta_type")
        fund = payload.get("fund", "")
        buckets = {}
        for row in (swg.items or []):
            if hta and row.get("hta_type") != hta:
                continue
            buckets.setdefault(row.get("package") or "Unassigned", []).append({
                "id": row.get("id"),
                "ref": row.get("ref", ""),
                "name": row.get("intervention", ""),
                "kind": row.get("kind", "intervention"),
                "service_type": row.get("service_type", ""),
                "package_access": row.get("package_access", ""),
                "routing": row.get("next_steps", ""),
                "decision": row.get("decision") or "pending",
                "comment": "",
            })
        out = []
        for name, items in buckets.items():
            obj = ProposedBenefitPackage.objects.filter(name=name, fund=fund).first()
            if obj:
                obj.items = items
                obj.data = {**(obj.data or {}), "source_swg": str(swg.id)}
                obj.save()
            else:
                obj = ProposedBenefitPackage.objects.create(
                    name=name, fund=fund, items=items,
                    data={"source_swg": str(swg.id)})
            out.append({"id": str(obj.id), "package": name, "count": len(items)})
        return bp_ok(out, "Built from SWG")

    # ---- promote: included only -> revised ----------------------------------
    @classmethod
    def promote(cls, pk):
        pkg = _get_or_404(ProposedBenefitPackage, pk)
        if not pkg:
            return bp_err("Proposed package not found", 404)
        keep = ("id", "ref", "name", "kind", "service_type", "package_access", "comment")
        included = [{k: it.get(k) for k in keep}
                    for it in (pkg.items or []) if it.get("decision") == "include"]
        if not included:
            return bp_err("No included interventions to promote", 400)
        rev = RevisedBenefitPackage.objects.filter(name=pkg.name, fund=pkg.fund).first()
        data = {**(pkg.data or {}), "promoted_from": str(pkg.id)}
        if rev:
            rev.items, rev.data = included, data
            rev.save()
        else:
            rev = RevisedBenefitPackage.objects.create(
                name=pkg.name, fund=pkg.fund, items=included, data=data)
        return bp_ok({"id": str(rev.id), "name": rev.name, "fund": rev.fund,
                    "items": rev.items})
        
        
class RevisedPackageService:
    @staticmethod
    def list(params):
        qs = RevisedBenefitPackage.objects.all()
        fund = (params or {}).get("fund")
        if fund:
            qs = qs.filter(fund=fund)
        return bp_ok([{"id": str(p.id), "name": p.name, "fund": p.fund,
                     "data": p.data or {}, "items": p.items or []} for p in qs])

    @staticmethod
    def get(pk):
        p = _get_or_404(RevisedBenefitPackage, pk)
        if not p:
            return bp_err("Revised package not found", 404)
        return bp_ok({"id": str(p.id), "name": p.name, "fund": p.fund,
                    "data": p.data or {}, "items": p.items or []})
