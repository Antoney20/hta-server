from app.models import (
    PanelAppraisedList, RevisedBenefitPackage,
)
from app.services.appraisal.benefits_package import bp_err, bp_ok
from app.services.appraisal_panel import _get_or_404


class AppraisedListService:
    DECISIONS = {"include", "exclude", "pending"}

    # ---- CRUD ---------------------------------------------------------------
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

    # ---- decision (single appraised row) ------------------------------------
    @classmethod
    def set_decision(cls, pk, payload):
        """Match on _key first (rows repeat per service, so ref alone isn't
        unique), then fall back to ref+service, then bare ref."""
        decision = (payload.get("decision") or "pending").lower()
        if decision not in cls.DECISIONS:
            return bp_err(f"decision must be one of {sorted(cls.DECISIONS)}", 400)
        a = _get_or_404(PanelAppraisedList, pk)
        if not a:
            return bp_err("Appraised list not found", 404)

        key = payload.get("_key")
        ref = payload.get("ref")
        service = payload.get("service")
        items = a.items or []

        def matches(it):
            if key and it.get("_key") == key:
                return True
            if key:
                return False
            if service is not None:
                return it.get("ref") == ref and (it.get("service") or "") == (service or "")
            return it.get("ref") == ref

        hit = next((it for it in items if matches(it)), None)
        if not hit:
            return bp_err("Appraised row not found", 404)
        hit["decision"] = decision
        if "comment" in payload:
            hit["comment"] = payload["comment"]
        a.items = items
        a.save(update_fields=["items", "updated_at"])
        return bp_ok(hit)

    # ---- build: included rows -> revised benefits packages ------------------
    @classmethod
    def build_revised(cls, pk, payload=None):
        a = _get_or_404(PanelAppraisedList, pk)
        if not a:
            return bp_err("Appraised list not found", 404)
        payload = payload or {}
        fund = payload.get("fund", "")
        included_only = payload.get("included_only", True)

        buckets = {}
        for row in (a.items or []):
            if included_only and (row.get("decision") or "").lower() != "include":
                continue
            pkg = row.get("package") or "Unassigned"
            buckets.setdefault(pkg, []).append({
                "id": row.get("id") or row.get("ref"),
                "ref": row.get("ref", ""),
                "name": row.get("intervention", ""),
                "kind": row.get("kind", "intervention"),
                "service_type": row.get("service", ""),
                "package_access": row.get("package_access", ""),
                "routing": row.get("recommendation", ""),
                "decision": row.get("decision") or "pending",
                "comment": row.get("comment") or row.get("rationale", ""),
            })

        if not buckets:
            return bp_err("No included interventions to build", 400)

        out = []
        for name, items in buckets.items():
            obj = RevisedBenefitPackage.objects.filter(name=name, fund=fund).first()
            if obj:
                obj.items = items
                obj.data = {**(obj.data or {}), "source_appraised": str(a.id)}
                obj.save()
            else:
                obj = RevisedBenefitPackage.objects.create(
                    name=name, fund=fund, items=items,
                    data={"source_appraised": str(a.id)})
            out.append({"id": str(obj.id), "package": name, "count": len(items)})
        return bp_ok(out, "Revised benefits packages built from appraisal report")

    # ---- revised (read-only) ------------------------------------------------
    @staticmethod
    def list_revised(params):
        qs = RevisedBenefitPackage.objects.all()
        fund = (params or {}).get("fund")
        if fund:
            qs = qs.filter(fund=fund)
        return bp_ok([{"id": str(p.id), "name": p.name, "fund": p.fund,
                     "data": p.data or {}, "items": p.items or []} for p in qs])

    @staticmethod
    def get_revised(pk):
        p = _get_or_404(RevisedBenefitPackage, pk)
        if not p:
            return bp_err("Revised package not found", 404)
        return bp_ok({"id": str(p.id), "name": p.name, "fund": p.fund,
                    "data": p.data or {}, "items": p.items or []})