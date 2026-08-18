import re

from app.models import PanelScoringRule, CriteriaAppraisalTool
from app.serializers import PanelScoringRuleSerializer


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(re.sub(r"[,\s]", "", str(v)))
    except (TypeError, ValueError):
        return None


class PanelRuleService:


    @staticmethod
    def list_rules(params):
        qs = PanelScoringRule.objects.all().order_by("criteria")
        if (active := params.get("active")) is not None:
            qs = qs.filter(active=str(active).lower() in ("1", "true", "yes"))
        if crit := params.get("criteria"):
            qs = qs.filter(criteria_key=PanelScoringRule.make_key(crit))
        return _ok(PanelScoringRuleSerializer(qs, many=True).data)

    @staticmethod
    def get_rule(pk):
        obj = _get_or_404(PanelScoringRule, pk)
        return _ok(PanelScoringRuleSerializer(obj).data) if obj else _err("not found", 404)

    @staticmethod
    def create_rule(payload):
        s = PanelScoringRuleSerializer(data=payload)
        if not s.is_valid():
            return _err(s.errors)
        s.save()
        return _ok(s.data, 201)

    @staticmethod
    def update_rule(pk, payload, partial):
        obj = _get_or_404(PanelScoringRule, pk)
        if not obj:
            return _err("not found", 404)
        s = PanelScoringRuleSerializer(obj, data=payload, partial=partial)
        if not s.is_valid():
            return _err(s.errors)
        s.save()
        return _ok(s.data)

    @staticmethod
    def delete_rule(pk):
        obj = _get_or_404(PanelScoringRule, pk)
        if not obj:
            return _err("not found", 404)
        obj.delete()
        return _ok(status=204)

    # ------------------------------------------------------- deterministic compute

    @staticmethod
    def _match_band(bands, value):
        """First band whose op matches `value` wins."""
        for b in bands:
            op, v = b.get("op"), b.get("value")
            try:
                if op == "between" and isinstance(v, (list, tuple)) and len(v) == 2:
                    if float(v[0]) <= value <= float(v[1]):
                        return b
                elif op == ">"  and value >  float(v): return b
                elif op == ">=" and value >= float(v): return b
                elif op == "<"  and value <  float(v): return b
                elif op == "<=" and value <= float(v): return b
                elif op == "==" and value == float(v): return b
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _match_combo(bands, codes):
        """Band whose combo set exactly matches the selected codes."""
        want = set(codes or [])
        for b in bands:
            if set(b.get("combo") or []) == want:
                return b
        return None

    @staticmethod
    def compute(rule, evidence=None, codes=None):
        """Deterministically resolve a rule to a score. Returns
        {score, label, value} or None when it can't fire (missing/non-numeric
        evidence, or no matching band)."""
        evidence = evidence or {}
        bands = rule.bands or []

        if rule.kind == PanelScoringRule.KIND_COMBO:
            b = PanelRuleService._match_combo(bands, codes)
            if not b:
                return None
            return {"score": b.get("score"), "label": b.get("label"), "value": list(codes or [])}

        # BAND — read target field(s), optionally sum, then match.
        fields = rule.target_fields or []
        nums = [_num(evidence.get(f)) for f in fields]
        nums = [n for n in nums if n is not None]
        if not nums:
            return None
        value = sum(nums) if (rule.aggregate == "sum") else nums[0]
        b = PanelRuleService._match_band(bands, value)
        if not b:
            return None
        return {"score": b.get("score"), "label": b.get("label"), "value": value}

    @staticmethod
    def resolve_option(rule, score):
        """The CriteriaAppraisalTool option (same criteria, matching score) that
        a computed score maps to — that option's id is the score FK."""
        if score is None:
            return None
        return (CriteriaAppraisalTool.objects
                .filter(criteria__iexact=rule.criteria, score=score, active=True)
                .first())

    @staticmethod
    def preview(payload):
        """Dry-run: compute a rule against supplied evidence/codes without
        writing anything. payload: {rule_id | rule, evidence, codes}."""
        rule = None
        if rid := payload.get("rule_id"):
            rule = _get_or_404(PanelScoringRule, rid)
        if not rule:
            return _err("rule not found", 404)
        result = PanelRuleService.compute(rule, payload.get("evidence"), payload.get("codes"))
        if not result:
            return _ok({"matched": False})
        opt = PanelRuleService.resolve_option(rule, result["score"])
        return _ok({
            "matched": True,
            "score": result["score"],
            "label": result["label"],
            "value": result["value"],
            "option_id": str(opt.id) if opt else None,
        })
        
    @staticmethod
    def bulk_import(payload):
        """Import an array of rules (the JSON the admin uploads). Each entry is
        matched to a criterion by name; existing rules for that criteria_key are
        replaced so re-uploading the file is idempotent. Returns per-row results."""
        rules = payload if isinstance(payload, list) else payload.get("rules")
        if not isinstance(rules, list):
            return _err("expected a list of rules")

        created, updated, failed = 0, 0, []
        for i, raw in enumerate(rules):
            if not isinstance(raw, dict):
                failed.append({"row": i, "error": "not an object"})
                continue
            name = (raw.get("criterion") or raw.get("criteria") or "").strip()
            if not name:
                failed.append({"row": i, "error": "missing criterion name"})
                continue

            aggregate = raw.get("aggregate") or ""
            has_combo_bands = any(isinstance(b, dict) and "combo" in b for b in (raw.get("bands") or []))
            kind = PanelScoringRule.KIND_COMBO if (aggregate == "combo" or has_combo_bands) \
                else PanelScoringRule.KIND_BAND

            data = {
                "criteria": name,
                "kind": kind,
                "description": raw.get("description") or "",
                "target_fields": raw.get("target_fields") or [],
                "aggregate": aggregate,
                "items": raw.get("items") or [],
                "bands": raw.get("bands") or [],
                "active": raw.get("active", True),
            }

            key = PanelScoringRule.make_key(name)
            existing = PanelScoringRule.objects.filter(criteria_key=key).first()
            s = PanelScoringRuleSerializer(existing, data=data) if existing \
                else PanelScoringRuleSerializer(data=data)
            if not s.is_valid():
                failed.append({"row": i, "criterion": name, "error": s.errors})
                continue
            s.save()
            updated += 1 if existing else 0
            created += 0 if existing else 1

        return _ok({"created": created, "updated": updated, "failed": failed})