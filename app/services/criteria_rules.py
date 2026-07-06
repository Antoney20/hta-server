from app.models import CriteriaAppraisalTool, CriteriaRule, CriteriaGuideDocument
from app.serializers import CriteriaRuleSerializer, CriteriaGuideDocumentSerializer


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()

KINDS = {"quantitative", "descriptive"}
AGGREGATES = {"", "average", "sum", "combo"}


class CriteriaRuleService:

    @staticmethod
    def _validate_kind(kind):
        if kind and kind not in KINDS:
            return f"kind must be one of: {', '.join(sorted(KINDS))}"
        return None

    @staticmethod
    def _validate_aggregate(agg):
        if agg not in AGGREGATES:
            return f"aggregate must be one of: {', '.join(a or '\"\"' for a in sorted(AGGREGATES))}"
        return None

    @staticmethod
    def _validate_target_fields(criterion, target_fields):
        """Every target field must be a real data label on the criterion."""
        if not target_fields:
            return None
        if not isinstance(target_fields, list):
            return "target_fields must be a list"
        allowed = {h.get("key") for h in (criterion.headers or []) if h.get("key")}
        if not allowed:
            return None   # criterion declares no headers yet — accept
        unknown = [f for f in target_fields if f not in allowed]
        return f"unknown target_fields: {', '.join(unknown)}" if unknown else None

    @staticmethod
    def _validate_items(items):
        if items in (None, []):            return None
        if not isinstance(items, list):    return "items must be a list"
        for it in items:
            if not isinstance(it, dict) or not it.get("key") or not it.get("label"):
                return "each item needs key + label"
        return None

    @staticmethod
    def _validate_bands(bands):
        if bands in (None, []):            return None
        if not isinstance(bands, list):    return "bands must be a list"
        for b in bands:
            if not isinstance(b, dict):    return "each band must be an object"
            has_combo = "combo" in b                      # equity factor-combo
            has_op    = "op" in b                         # quantitative threshold
            has_label = "label" in b                      # descriptive prose band
            if not (has_combo or has_op or has_label):
                return "each band needs one of: 'combo', 'op', or 'label'"
            if "score" not in b:
                return "each band needs a score"
        return None

    @staticmethod
    def _validate(criterion, payload):
        for check in (
            CriteriaRuleService._validate_kind(payload.get("kind")),
            CriteriaRuleService._validate_aggregate(payload.get("aggregate", "")),
            CriteriaRuleService._validate_target_fields(criterion, payload.get("target_fields")),
            CriteriaRuleService._validate_items(payload.get("items")),
            CriteriaRuleService._validate_bands(payload.get("bands")),
        ):
            if check:
                return check
        return None

    @staticmethod
    def list_rules(params):
        qs = CriteriaRule.objects.select_related("criterion").prefetch_related("documents")
        if criterion := params.get("criterion"):
            qs = qs.filter(criterion_id=criterion)
        active = params.get("active")
        if active is not None:
            qs = qs.filter(active=str(active).lower() in ("1", "true", "yes"))
        return _ok(CriteriaRuleSerializer(qs.order_by("criterion__criteria"), many=True).data)

    @staticmethod
    def get_rule(pk):
        obj = _get_or_404(CriteriaRule, pk)
        return _ok(CriteriaRuleSerializer(obj).data) if obj else _err("not found", 404)

    @staticmethod
    def create_rule(payload):
        criterion = _get_or_404(CriteriaAppraisalTool, payload.get("criterion"))
        if not criterion:
            return _err("criterion not found", 404)
        if err := CriteriaRuleService._validate(criterion, payload):
            return _err(err)
        s = CriteriaRuleSerializer(data=payload)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data, 201)

    @staticmethod
    def update_rule(pk, payload, partial):
        obj = _get_or_404(CriteriaRule, pk)
        if not obj: return _err("not found", 404)
        if err := CriteriaRuleService._validate(obj.criterion, payload):
            return _err(err)
        s = CriteriaRuleSerializer(obj, data=payload, partial=partial)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data)

    @staticmethod
    def delete_rule(pk):
        obj = _get_or_404(CriteriaRule, pk)
        if not obj: return _err("not found", 404)
        obj.delete()
        return _ok(status=204)

    @staticmethod
    def bulk_upsert_rules(rows):
        """
        Each row targets a criterion by name (or id). One rule per criterion —
        upsert so re-running the same payload edits in place rather than duplicating.
        """
        if not isinstance(rows, list):
            return _err("expected a list of rules")

        created, updated, failed = 0, 0, []
        for i, row in enumerate(rows):
            criterion = CriteriaRuleService._resolve_criterion(row)
            if not criterion:
                failed.append({"row": i, "error": "criterion not found"})
                continue
            if err := CriteriaRuleService._validate(criterion, row):
                failed.append({"row": i, "error": err})
                continue

            existed = CriteriaRule.objects.filter(criterion=criterion).exists()
            CriteriaRule.objects.update_or_create(
                criterion=criterion,
                defaults={
                    "description":   row.get("description", ""),
                    "kind":          row.get("kind", "descriptive"),
                    "target_fields": row.get("target_fields", []),
                    "aggregate":     row.get("aggregate", ""),
                    "items":         row.get("items", []),
                    "bands":         row.get("bands", []),
                    "active":        row.get("active", True),
                },
            )
            updated += 1 if existed else 0
            created += 0 if existed else 1

        return _ok({"created": created, "updated": updated, "failed": failed})

    @staticmethod
    def _resolve_criterion(row):
        name = row.get("criterion") or row.get("criterion_name") or row.get("criteria")
        if not name:
            return None
        return (
            CriteriaAppraisalTool.objects
            .filter(criteria__iexact=str(name).strip())
            .order_by("created_at")
            .first()
        ) 

    @staticmethod
    def add_document(rule_pk, payload, file=None, request=None):
        rule = _get_or_404(CriteriaRule, rule_pk)
        if not rule: return _err("rule not found", 404)
        data = {
            "rule": rule.id,
            "label": payload.get("label", ""),
            "description": payload.get("description", ""),
            "link": payload.get("link", ""),
        }
        if file is not None:
            data["file"] = file
        s = CriteriaGuideDocumentSerializer(data=data, context={"request": request})
        if not s.is_valid(): return _err(s.errors)
        s.save()
        return _ok(s.data, 201)

    @staticmethod
    def delete_document(pk):
        obj = _get_or_404(CriteriaGuideDocument, pk)
        if not obj: return _err("not found", 404)
        if obj.file:
            obj.file.delete(save=False)
        obj.delete()
        return _ok(status=204)