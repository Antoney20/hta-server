from app.models import CriteriaAppraisalTool, CriterionEvidence, InterventionProposal, NationalProgramProposal
from app.serializers import CriteriaAppraisalToolSerializer, CriterionEvidenceSerializer


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


class AppraisalPanelService:

    @staticmethod
    def _validate_headers(headers):
        if headers in (None, []):         return None
        if not isinstance(headers, list): return "headers must be a list"
        for h in headers:
            if not isinstance(h, dict) or not h.get("key") or not h.get("label"):
                return "each header needs key + label"
        return None

    @staticmethod
    def _validate_evidence_data(criterion, data):
        allowed = {h.get("key") for h in (criterion.headers or []) if h.get("key")}
        if not allowed:                   return None          # no schema declared → accept
        unknown = set(data or {}) - allowed
        return f"unknown keys: {', '.join(sorted(unknown))}" if unknown else None

    @staticmethod
    def _resolve_target(row):
        iv, npr = row.get("intervention"), row.get("national_proposal")
        if bool(iv) == bool(npr):
            return None, "exactly one of intervention / national_proposal required"
        if iv:
            obj = _get_or_404(InterventionProposal, iv)
            return ({"intervention": obj}, None) if obj else (None, "intervention not found")
        obj = _get_or_404(NationalProgramProposal, npr)
        return ({"national_proposal": obj}, None) if obj else (None, "national_proposal not found")

    @staticmethod
    def list_criteria(params):
        qs = CriteriaAppraisalTool.objects.all().order_by("criteria")
        active = params.get("active")
        if active is not None:
            qs = qs.filter(active=str(active).lower() in ("1", "true", "yes"))
        return _ok(CriteriaAppraisalToolSerializer(qs, many=True).data)

    @staticmethod
    def get_criterion(pk):
        obj = _get_or_404(CriteriaAppraisalTool, pk)
        return _ok(CriteriaAppraisalToolSerializer(obj).data) if obj else _err("not found", 404)

    @staticmethod
    def create_criterion(payload):
        if err := AppraisalPanelService._validate_headers(payload.get("headers")):
            return _err(err)
        s = CriteriaAppraisalToolSerializer(data=payload)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data, 201)

    @staticmethod
    def update_criterion(pk, payload, partial):
        obj = _get_or_404(CriteriaAppraisalTool, pk)
        if not obj: return _err("not found", 404)
        if "headers" in payload and (err := AppraisalPanelService._validate_headers(payload.get("headers"))):
            return _err(err)
        s = CriteriaAppraisalToolSerializer(obj, data=payload, partial=partial)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data)

    @staticmethod
    def configure_criterion(pk, payload):
        """Panel-only: whitelists the fields the panel page controls."""
        obj = _get_or_404(CriteriaAppraisalTool, pk)
        if not obj: return _err("not found", 404)
        allowed = {"headers", "active", "scoring_approach", "score", "description"}
        clean = {k: v for k, v in payload.items() if k in allowed}
        if "headers" in clean and (err := AppraisalPanelService._validate_headers(clean["headers"])):
            return _err(err)
        s = CriteriaAppraisalToolSerializer(obj, data=clean, partial=True)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data)

    @staticmethod
    def delete_criterion(pk):
        obj = _get_or_404(CriteriaAppraisalTool, pk)
        if not obj: return _err("not found", 404)
        if obj.evidence.exists(): return _err("criterion has evidence; cannot delete", 409)
        obj.delete()
        return _ok(status=204)

    @staticmethod
    def list_evidence(params):
        qs = CriterionEvidence.objects.select_related("criterion").order_by("-updated_at")
        for f in ("criterion", "intervention", "national_proposal"):
            if v := params.get(f): qs = qs.filter(**{f: v})
        return _ok(CriterionEvidenceSerializer(qs, many=True).data)

    @staticmethod
    def _upsert_evidence(row):
        criterion = _get_or_404(CriteriaAppraisalTool, row.get("criterion"))
        if not criterion: return None, "criterion not found"
        target, err = AppraisalPanelService._resolve_target(row)
        if err: return None, err
        data = row.get("data") or {}
        if err := AppraisalPanelService._validate_evidence_data(criterion, data):
            return None, err
        obj, _ = CriterionEvidence.objects.update_or_create(
            criterion=criterion, **target,
            defaults={"data": data, "score": row.get("score")},
        )
        return obj, None

    @staticmethod
    def create_evidence(payload):
        obj, err = AppraisalPanelService._upsert_evidence(payload)
        return _err(err) if err else _ok(CriterionEvidenceSerializer(obj).data, 201)

    @staticmethod
    def update_evidence(pk, payload, partial):
        obj = _get_or_404(CriterionEvidence, pk)
        if not obj: return _err("not found", 404)
        if "data" in payload and (err := AppraisalPanelService._validate_evidence_data(obj.criterion, payload["data"])):
            return _err(err)
        s = CriterionEvidenceSerializer(obj, data=payload, partial=partial)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data)

    @staticmethod
    def delete_evidence(pk):
        obj = _get_or_404(CriterionEvidence, pk)
        if not obj: return _err("not found", 404)
        obj.delete()
        return _ok(status=204)

    @staticmethod
    def bulk_upload_evidence(rows):
        if not isinstance(rows, list): return _err("expected a list of rows")
        created, updated, failed = 0, 0, []
        for i, row in enumerate(rows):
            existed = CriterionEvidence.objects.filter(
                criterion=row.get("criterion"),
                intervention=row.get("intervention"),
                national_proposal=row.get("national_proposal"),
            ).exists()
            obj, err = AppraisalPanelService._upsert_evidence(row)
            if err: failed.append({"row": i, "error": err})
            elif existed: updated += 1
            else: created += 1
        return _ok({"created": created, "updated": updated, "failed": failed})

    @staticmethod
    def bulk_delete_evidence(ids):
        if not isinstance(ids, list): return _err("expected a list of ids")
        n, _ = CriterionEvidence.objects.filter(id__in=ids).delete()
        return _ok({"deleted": n})
    