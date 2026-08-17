from app.models import (
    PanelAppraisalScore, CriteriaAppraisalTool,
    InterventionProposal, NationalProgramProposal,
)
from app.serializers import PanelAppraisalScoreSerializer


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


class PanelScoreService:

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
    def _prepare(row):
        criteria = _get_or_404(CriteriaAppraisalTool, row.get("criteria"))
        if not criteria:
            return None, None, "criteria not found"
        target, err = PanelScoreService._resolve_target(row)
        if err:
            return None, None, err
        return criteria, target, None

    @staticmethod
    def list_scores(params):
        qs = (PanelAppraisalScore.objects
              .select_related("criteria", "reviewer", "intervention", "national_proposal")
              .order_by("-updated_at"))
        for f in ("criteria", "intervention", "national_proposal", "reviewer"):
            if v := params.get(f):
                qs = qs.filter(**{f: v})
        if (svc := params.get("service")) is not None:
            qs = qs.filter(service_key=PanelAppraisalScore.make_service_key(svc))
        return _ok(PanelAppraisalScoreSerializer(qs, many=True).data)

    @staticmethod
    def get_score(pk):
        obj = _get_or_404(PanelAppraisalScore, pk)
        return _ok(PanelAppraisalScoreSerializer(obj).data) if obj else _err("not found", 404)

    @staticmethod
    def _upsert(row, reviewer):
        """One record per (reviewer, target, criteria, service_key): update in
        place, or create if absent. Duplicates across services survive because
        service_key is part of the natural key."""
        criteria, target, err = PanelScoreService._prepare(row)
        if err:
            return None, err
        svc = row.get("service") or ""
        obj, _ = PanelAppraisalScore.objects.update_or_create(
            reviewer=reviewer, criteria=criteria, **target,
            service_key=PanelAppraisalScore.make_service_key(svc),
            defaults={
                "service": svc,
                "score": row.get("score") or {},
                "comment": row.get("comment") or "",
            },
        )
        return obj, None

    @staticmethod
    def create_score(payload, reviewer):
        obj, err = PanelScoreService._upsert(payload, reviewer)
        return _err(err) if err else _ok(PanelAppraisalScoreSerializer(obj).data, 201)

    @staticmethod
    def update_score(pk, payload, reviewer, partial):
        obj = _get_or_404(PanelAppraisalScore, pk)
        if not obj:
            return _err("not found", 404)
        if "criteria" in payload and (c := _get_or_404(CriteriaAppraisalTool, payload["criteria"])):
            obj.criteria = c
        if "service" in payload:
            obj.service = payload["service"] or ""
        if "score" in payload:
            obj.score = payload["score"] or {}
        if "comment" in payload:
            obj.comment = payload["comment"] or ""
        obj.save()
        return _ok(PanelAppraisalScoreSerializer(obj).data)

    @staticmethod
    def delete_score(pk):
        obj = _get_or_404(PanelAppraisalScore, pk)
        if not obj:
            return _err("not found", 404)
        obj.delete()
        return _ok(status=204)

    @staticmethod
    def bulk_upsert(rows, reviewer):
        if not isinstance(rows, list):
            return _err("expected a list of rows")
        created, failed = 0, []
        for i, row in enumerate(rows):
            obj, err = PanelScoreService._upsert(row, reviewer)
            if err:
                failed.append({"row": i, "error": err})
            else:
                created += 1
        return _ok({"upserted": created, "failed": failed})

    @staticmethod
    def bulk_delete(ids):
        if not isinstance(ids, list):
            return _err("expected a list of ids")
        n, _ = PanelAppraisalScore.objects.filter(id__in=ids).delete()
        return _ok({"deleted": n})