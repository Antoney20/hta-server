from django.db.models import Count

from app.models import (
    DecisionTemplate,
    CriteriaRule, CriterionEvidence,
    InterventionProposal, NationalProgramProposal,
)


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


def _abs(request, url):
    if not url:
        return None
    return request.build_absolute_uri(url) if (request and str(url).startswith("/")) else url


class DecisionTemplateService:
    @staticmethod
    def list_templates(params, request=None):
        kind = (params.get("kind") or "").lower() if params else ""

        rows = []
        if kind in ("", "intervention"):
            counts = {
                r["intervention_id"]: r["n"]
                for r in (CriterionEvidence.objects.filter(intervention__isnull=False)
                          .values("intervention_id")
                          .annotate(n=Count("criterion_id", distinct=True)))
            }
            for t in (InterventionProposal.objects.filter(id__in=counts)
                      .select_related("package", "phase")):
                rows.append(DecisionTemplateService._row("intervention", t, counts[t.id]))

        if kind in ("", "national_proposal"):
            counts = {
                r["national_proposal_id"]: r["n"]
                for r in (CriterionEvidence.objects.filter(national_proposal__isnull=False)
                          .values("national_proposal_id")
                          .annotate(n=Count("criterion_id", distinct=True)))
            }
            for t in (NationalProgramProposal.objects.filter(id__in=counts)
                      .select_related("package", "phase")):
                rows.append(DecisionTemplateService._row("national_proposal", t, counts[t.id]))

        return _ok({"count": len(rows), "targets": rows})


    @staticmethod
    def get_template(pk, request=None):
        t = (InterventionProposal.objects.filter(pk=pk)
             .select_related("package", "phase").first())
        kind = "intervention"
        if not t:
            t = (NationalProgramProposal.objects.filter(pk=pk)
                 .select_related("package", "phase").first())
            kind = "national_proposal"
        if not t:
            return _err("not found", 404)

        rule_by_crit = DecisionTemplateService._rules()
        return _ok(DecisionTemplateService._target(kind, t, rule_by_crit, request))

    @staticmethod
    def generate(payload, request=None, user=None):
        """
        Clean evidence payload per target. No scores. payload (all optional):
          interventions / national_proposals : subset of targets; else all with evidence.
        """
        payload = payload or {}
        only_iv = {str(i) for i in (payload.get("interventions") or [])}
        only_np = {str(i) for i in (payload.get("national_proposals") or [])}

        iv_ids = set(CriterionEvidence.objects.filter(intervention__isnull=False)
                     .values_list("intervention_id", flat=True))
        np_ids = set(CriterionEvidence.objects.filter(national_proposal__isnull=False)
                     .values_list("national_proposal_id", flat=True))
        if only_iv or only_np:
            iv_ids = {i for i in iv_ids if str(i) in only_iv}
            np_ids = {i for i in np_ids if str(i) in only_np}

        rule_by_crit = DecisionTemplateService._rules()
        targets = []
        for t in (InterventionProposal.objects.filter(id__in=iv_ids)
                  .select_related("package", "phase")):
            targets.append(DecisionTemplateService._target("intervention", t, rule_by_crit, request))
        for t in (NationalProgramProposal.objects.filter(id__in=np_ids)
                  .select_related("package", "phase")):
            targets.append(DecisionTemplateService._target("national_proposal", t, rule_by_crit, request))

        return _ok({"count": len(targets), "targets": targets})

    @staticmethod
    def delete_template(pk):
        obj = _get_or_404(DecisionTemplate, pk)
        if not obj:
            return _err("not found", 404)
        obj.delete()
        return _ok(status=204)

    @staticmethod
    def _rules():
        return {
            r.criterion_id: r
            for r in CriteriaRule.objects.filter(active=True).prefetch_related("documents")
        }

    @staticmethod
    def _row(kind, t, criteria_count):
        return {
            "id": str(t.id),
            "reference_number": getattr(t, "reference_number", None),
            "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
            "kind": kind,
            "package": getattr(getattr(t, "package", None), "name", None),
            "phase": getattr(getattr(t, "phase", None), "name", None),
            "criteria_count": criteria_count,
        }


    @staticmethod
    def _target(kind, t, rule_by_crit, request):
        field = "intervention" if kind == "intervention" else "national_proposal"
        ev_qs = (CriterionEvidence.objects.filter(**{field: t})
                 .select_related("criterion")
                 .order_by("criterion__criteria"))

        groups = {}
        for ev in ev_qs:
            name = (getattr(ev.criterion, "criteria", "") or "").strip()
            key = name.lower()
            rule = rule_by_crit.get(ev.criterion_id)
            g = groups.get(key)
            if not g:
                g = {
                    "id": str(ev.criterion_id),
                    "criterion": name,
                    "type": rule.kind if rule else "descriptive",
                    "target_fields": [],  
                    "evidence": {},
                    "guides": DecisionTemplateService._guides(rule, request),
                }
                groups[key] = g
            for f in (rule.target_fields or [] if rule else []):
                if f not in g["target_fields"]:
                    g["target_fields"].append(f)
            DecisionTemplateService._absorb(g["evidence"], ev)

        return {
            "id": str(t.id),
            "reference_number": getattr(t, "reference_number", None),
            "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
            "kind": kind,
            "package": getattr(getattr(t, "package", None), "name", None),
            "phase": getattr(getattr(t, "phase", None), "name", None),
            "criteria": list(groups.values()),
        }


    @staticmethod
    def _absorb(bag, ev):
        data = ev.data if isinstance(ev.data, dict) else {}
        for k, v in data.items():
            DecisionTemplateService._add_field(bag, k, v)

    @staticmethod
    def _add_field(bag, key, value):
        """List them well when multiple values land on the same field."""
        if value in (None, "", [], {}):
            return
        if key not in bag:
            bag[key] = value
            return
        cur = bag[key] if isinstance(bag[key], list) else [bag[key]]
        add = value if isinstance(value, list) else [value]
        bag[key] = cur + [x for x in add if x not in cur]

    @staticmethod
    def _guides(rule, request):
        """Guide materials live on CriteriaGuideDocument (rule.documents)."""
        if not rule:
            return []
        out = []
        for d in rule.documents.all():
            f = getattr(d, "file", None)
            out.append({
                "label": d.label,
                "description": d.description or None,
                "link": d.link or None,
                "file": _abs(request, f.url if f else None),
            })
        return out