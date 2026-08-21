# from django.db.models import Count

# from app.models import (
#     DecisionTemplate,
#     CriteriaRule, CriterionEvidence,
#     InterventionProposal, NationalProgramProposal,
# )


# def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
# def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
# def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


# def _abs(request, url):
#     if not url:
#         return None
#     return request.build_absolute_uri(url) if (request and str(url).startswith("/")) else url


# class DecisionTemplateService:
#     @staticmethod
#     def list_templates(params, request=None):
#         kind = (params.get("kind") or "").lower() if params else ""

#         rows = []
#         if kind in ("", "intervention"):
#             counts = {
#                 r["intervention_id"]: r["n"]
#                 for r in (CriterionEvidence.objects.filter(intervention__isnull=False)
#                           .values("intervention_id")
#                           .annotate(n=Count("criterion_id", distinct=True)))
#             }
#             for t in (InterventionProposal.objects.filter(id__in=counts)
#                       .select_related("package", "phase")):
#                 rows.append(DecisionTemplateService._row("intervention", t, counts[t.id]))

#         if kind in ("", "national_proposal"):
#             counts = {
#                 r["national_proposal_id"]: r["n"]
#                 for r in (CriterionEvidence.objects.filter(national_proposal__isnull=False)
#                           .values("national_proposal_id")
#                           .annotate(n=Count("criterion_id", distinct=True)))
#             }
#             for t in (NationalProgramProposal.objects.filter(id__in=counts)
#                       .select_related("package", "phase")):
#                 rows.append(DecisionTemplateService._row("national_proposal", t, counts[t.id]))

#         return _ok({"count": len(rows), "targets": rows})


#     @staticmethod
#     def get_template(pk, request=None, can_regenerate=False):
#         t = (InterventionProposal.objects.filter(pk=pk)
#              .select_related("package", "phase").first())
#         kind = "intervention"
#         if not t:
#             t = (NationalProgramProposal.objects.filter(pk=pk)
#                  .select_related("package", "phase").first())
#             kind = "national_proposal"
#         if not t:
#             return _err("not found", 404)

#         rule_by_crit = DecisionTemplateService._rules()
#         return _ok(DecisionTemplateService._target(kind, t, rule_by_crit, request))


#     @staticmethod
#     def scoring_template(pk, request=None):
#         """Evidence for the PANEL SCORING detail page. Same target envelope as
#         `get_template`, but each criterion's `evidence` is a LIST — one item per
#         uploaded record, each carrying that record's own scalar data (via
#         `_child`). No merged bag, no `children`, no `service_rows`. This is the
#         un-zipped shape: two records under one criterion stay two items, never a
#         `[95, 272]` field list. Kept separate from `_target` so the export /
#         general grid and the overview list are untouched."""
#         t = (InterventionProposal.objects.filter(pk=pk)
#              .select_related("package", "phase").first())
#         kind = "intervention"
#         if not t:
#             t = (NationalProgramProposal.objects.filter(pk=pk)
#                  .select_related("package", "phase").first())
#             kind = "national_proposal"
#         if not t:
#             return _err("not found", 404)

#         rule_by_crit = DecisionTemplateService._rules()
#         return _ok(DecisionTemplateService._scoring_target(kind, t, rule_by_crit, request))


#     @staticmethod
#     def detailed_info(pk, request=None):
#         """Full evidence for one target — same EvidenceTarget shape as
#         get_template, but nothing is trimmed. `target_fields` is the union of
#         every field submitted (not just the rule's important subset) and each
#         record's evidence is the raw `data` (empty values kept). This is the
#         "everything the proposer submitted" view, not the cleaned summary."""
#         t = (InterventionProposal.objects.filter(pk=pk)
#              .select_related("package", "phase").first())
#         kind = "intervention"
#         if not t:
#             t = (NationalProgramProposal.objects.filter(pk=pk)
#                  .select_related("package", "phase").first())
#             kind = "national_proposal"
#         if not t:
#             return _err("not found", 404)

#         rule_by_crit = DecisionTemplateService._rules()
#         field = "intervention" if kind == "intervention" else "national_proposal"
#         ev_qs = (CriterionEvidence.objects.filter(**{field: t})
#                  .select_related("criterion")
#                  .order_by("criterion__criteria", "created_at", "id"))

#         groups = {}
#         for ev in ev_qs:
#             name = (getattr(ev.criterion, "criteria", "") or "").strip()
#             key = name.lower()
#             rule = rule_by_crit.get(ev.criterion_id)
#             g = groups.get(key)
#             if not g:
#                 g = {
#                     "id": str(ev.criterion_id),
#                     "criterion": name,
#                     "type": rule.kind if rule else "descriptive",
#                     # rule fields first, then every other submitted key appended below
#                     "target_fields": list(rule.target_fields or []) if rule else [],
#                     "evidence": {},   # merged view — raw, empties kept
#                     "children": [],   # every record, raw data untouched
#                     "guides": DecisionTemplateService._guides(rule, request),
#                 }
#                 groups[key] = g

#             data = ev.data if isinstance(ev.data, dict) else {}
#             for k in data.keys():
#                 if k not in g["target_fields"]:
#                     g["target_fields"].append(k)
#             for k, v in data.items():
#                 DecisionTemplateService._merge_raw(g["evidence"], k, v)
#             g["children"].append({
#                 "evidence_id": str(ev.id),
#                 "score": getattr(ev, "score", None),
#                 "created_at": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
#                 "evidence": dict(data),  # RAW — nothing dropped, nothing merged
#             })

#         return _ok({
#             "id": str(t.id),
#             "reference_number": getattr(t, "reference_number", None),
#             "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
#             "kind": kind,
#             "package": getattr(getattr(t, "package", None), "name", None),
#             "phase": getattr(getattr(t, "phase", None), "name", None),
#             "criteria": list(groups.values()),
#         })

#     @staticmethod
#     def _merge_raw(bag, key, value):
#         """Merge for the detailed view — unlike _add_field it does NOT drop
#         empty values, so blank fields still surface. Distinct values on the
#         same key collect into a list."""
#         if key not in bag:
#             bag[key] = value
#             return
#         cur = bag[key] if isinstance(bag[key], list) else [bag[key]]
#         add = value if isinstance(value, list) else [value]
#         bag[key] = cur + [x for x in add if x not in cur]

#     @staticmethod
#     def generate(payload, request=None, user=None):
#         """
#         Clean evidence payload per target. No scores. payload (all optional):
#           interventions / national_proposals : subset of targets; else all with evidence.
#         """
#         payload = payload or {}
#         only_iv = {str(i) for i in (payload.get("interventions") or [])}
#         only_np = {str(i) for i in (payload.get("national_proposals") or [])}

#         iv_ids = set(CriterionEvidence.objects.filter(intervention__isnull=False)
#                      .values_list("intervention_id", flat=True))
#         np_ids = set(CriterionEvidence.objects.filter(national_proposal__isnull=False)
#                      .values_list("national_proposal_id", flat=True))
#         if only_iv or only_np:
#             iv_ids = {i for i in iv_ids if str(i) in only_iv}
#             np_ids = {i for i in np_ids if str(i) in only_np}

#         rule_by_crit = DecisionTemplateService._rules()
#         targets = []
#         for t in (InterventionProposal.objects.filter(id__in=iv_ids)
#                   .select_related("package", "phase")):
#             targets.append(DecisionTemplateService._target("intervention", t, rule_by_crit, request))
#         for t in (NationalProgramProposal.objects.filter(id__in=np_ids)
#                   .select_related("package", "phase")):
#             targets.append(DecisionTemplateService._target("national_proposal", t, rule_by_crit, request))

#         return _ok({"count": len(targets), "targets": targets})

#     @staticmethod
#     def delete_template(pk):
#         obj = _get_or_404(DecisionTemplate, pk)
#         if not obj:
#             return _err("not found", 404)
#         obj.delete()
#         return _ok(status=204)

#     @staticmethod
#     def _rules():
#         return {
#             r.criterion_id: r
#             for r in CriteriaRule.objects.filter(active=True).prefetch_related("documents")
#         }

#     @staticmethod
#     def _row(kind, t, criteria_count):
#         return {
#             "id": str(t.id),
#             "reference_number": getattr(t, "reference_number", None),
#             "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
#             "kind": kind,
#             "package": getattr(getattr(t, "package", None), "name", None),
#             "phase": getattr(getattr(t, "phase", None), "name", None),
#             "criteria_count": criteria_count,
#         }


#     @staticmethod
#     def _target(kind, t, rule_by_crit, request):
#         field = "intervention" if kind == "intervention" else "national_proposal"
#         ev_qs = (CriterionEvidence.objects.filter(**{field: t})
#                  .select_related("criterion")
#                  .order_by("criterion__criteria"))

#         groups = {}
#         # per-service rows for the general/export view. we DON'T merge or clean
#         # here — each uploaded evidence record is kept as it was uploaded, then
#         # grouped by its own service. so field values stay row-aligned and no
#         # value zips across services (the "4 values" bug).
#         service_buckets = {}
#         for ev in ev_qs:
#             name = (getattr(ev.criterion, "criteria", "") or "").strip()
#             key = name.lower()
#             rule = rule_by_crit.get(ev.criterion_id)
#             g = groups.get(key)
#             if not g:
#                 g = {
#                     "id": str(ev.criterion_id),
#                     "criterion": name,
#                     "type": rule.kind if rule else "descriptive",
#                     "target_fields": [],
#                     # merged view — every record for this criterion folded together.
#                     # kept exactly as before so existing consumers are unaffected.
#                     "evidence": {},
#                     # one entry per evidence record, kept whole. lets criteria that
#                     # carry more than one record (duplicates) be rendered individually
#                     # instead of only as the merged bag above.
#                     "children": [],
#                     "guides": DecisionTemplateService._guides(rule, request),
#                 }
#                 groups[key] = g
#             for f in (rule.target_fields or [] if rule else []):
#                 if f not in g["target_fields"]:
#                     g["target_fields"].append(f)
#             DecisionTemplateService._absorb(g["evidence"], ev)
#             g["children"].append(DecisionTemplateService._child(ev))

#             # bucket this record under its own service, kept RAW (exactly as
#             # uploaded — no merge, no cleaning). first record for a given
#             # service+criterion wins; duplicates stay visible via `children`.
#             data = ev.data if isinstance(ev.data, dict) else {}
#             skey, sdisp = DecisionTemplateService._service_of(data)
#             sb = service_buckets.setdefault(
#                 skey, {"service": sdisp, "service_key": skey, "criteria": {}}
#             )
#             sb["criteria"].setdefault(key, dict(data))

#         return {
#             "id": str(t.id),
#             "reference_number": getattr(t, "reference_number", None),
#             "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
#             "kind": kind,
#             "package": getattr(getattr(t, "package", None), "name", None),
#             "phase": getattr(getattr(t, "phase", None), "name", None),
#             "criteria": list(groups.values()),
#             # raw evidence rows grouped by service for the general/export grid.
#             # one entry per distinct service; `criteria` maps criterion-name
#             # (lowercased, matching the frontend column key) -> that record's
#             # raw uploaded data (empties kept).
#             "service_rows": list(service_buckets.values()),
#         }


#     @staticmethod
#     def _scoring_target(kind, t, rule_by_crit, request):
#         """Builder for `scoring_template`. Same envelope as `_target`, but each
#         criterion's `evidence` is a LIST of whole records (scalar, un-zipped) —
#         no merged bag, no `children`, no `service_rows`. `_child`/`_record` do
#         the per-record cleaning, so nothing merges across records."""
#         field = "intervention" if kind == "intervention" else "national_proposal"
#         ev_qs = (CriterionEvidence.objects.filter(**{field: t})
#                  .select_related("criterion")
#                  .order_by("criterion__criteria", "created_at", "id"))

#         groups = {}
#         for ev in ev_qs:
#             name = (getattr(ev.criterion, "criteria", "") or "").strip()
#             key = name.lower()
#             rule = rule_by_crit.get(ev.criterion_id)
#             g = groups.get(key)
#             if not g:
#                 g = {
#                     "id": str(ev.criterion_id),
#                     "criterion": name,
#                     "type": rule.kind if rule else "descriptive",
#                     "target_fields": [],
#                     # ONE ITEM PER UPLOADED RECORD, in upload order. Each item is
#                     # that record's own scalar data (empties dropped). Two records
#                     # → two items, never `[95, 272]`.
#                     "evidence": [],
#                     "guides": DecisionTemplateService._guides(rule, request),
#                 }
#                 groups[key] = g
#             for f in (rule.target_fields or [] if rule else []):
#                 if f not in g["target_fields"]:
#                     g["target_fields"].append(f)
#             g["evidence"].append(DecisionTemplateService._child(ev))

#         return {
#             "id": str(t.id),
#             "reference_number": getattr(t, "reference_number", None),
#             "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
#             "kind": kind,
#             "package": getattr(getattr(t, "package", None), "name", None),
#             "phase": getattr(getattr(t, "phase", None), "name", None),
#             "criteria": list(groups.values()),
#         }


#     @staticmethod
#     def _service_of(data):
#         """Normalized service for row-splitting. Returns (key, display).
#         `key` is lowercase-alphanumeric only, so spelling/spacing variants
#         collapse to one row (mirrors the frontend service-key normalization).
#         Records with no service land under the "" key (the No-service row)."""
#         v = data.get("service") if isinstance(data, dict) else None
#         if isinstance(v, list):
#             v = next((x for x in v if x not in (None, "")), "")
#         v = v if isinstance(v, str) else ("" if v is None else str(v))
#         disp = v.strip()
#         key = "".join(ch for ch in disp.lower() if ch.isalnum())
#         return key, disp


#     @staticmethod
#     def _absorb(bag, ev):
#         data = ev.data if isinstance(ev.data, dict) else {}
#         for k, v in data.items():
#             DecisionTemplateService._add_field(bag, k, v)

#     @staticmethod
#     def _child(ev):
#         """One evidence record, kept intact — the unit that lets duplicates render
#         as separate children rather than collapsing into the merged bag."""
#         return {
#             "evidence_id": str(ev.id),
#             "score": getattr(ev, "score", None),
#             "created_at": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
#             "evidence": DecisionTemplateService._record(ev),
#         }

#     @staticmethod
#     def _record(ev):
#         """Non-empty fields of a single evidence row — same per-field cleaning as
#         the merged bag, but for one record only (no cross-record list merging)."""
#         bag = {}
#         data = ev.data if isinstance(ev.data, dict) else {}
#         for k, v in data.items():
#             DecisionTemplateService._add_field(bag, k, v)
#         return bag

#     @staticmethod
#     def _add_field(bag, key, value):
#         """List them well when multiple values land on the same field."""
#         if value in (None, "", [], {}):
#             return
#         if key not in bag:
#             bag[key] = value
#             return
#         cur = bag[key] if isinstance(bag[key], list) else [bag[key]]
#         add = value if isinstance(value, list) else [value]
#         bag[key] = cur + [x for x in add if x not in cur]

#     @staticmethod
#     def _guides(rule, request):
#         """Guide materials live on CriteriaGuideDocument (rule.documents)."""
#         if not rule:
#             return []
#         out = []
#         for d in rule.documents.all():
#             f = getattr(d, "file", None)
#             out.append({
#                 "label": d.label,
#                 "description": d.description or None,
#                 "link": d.link or None,
#                 "file": _abs(request, f.url if f else None),
#             })
#         return out

#     @classmethod
#     def evidence_for_target(cls, target_type: str, target_id: str, request=None) -> dict:
#         """
#         One target's full evidence payload — the same EvidenceTarget the detail
#         endpoint returns (criteria, each with target_fields, evidence, guides).
#         Resolves the target, then delegates to the single-target builder (`_target`).
#         """
#         model = InterventionProposal if target_type == "intervention" else NationalProgramProposal
#         t = (model.objects.filter(pk=target_id)
#              .select_related("package", "phase").first())
#         if not t:
#             raise ValueError(f"{target_type} {target_id} not found")
#         return cls._target(target_type, t, cls._rules(), request)


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

        iv_cov, np_cov = DecisionTemplateService._assessment_coverage()

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
                rows.append(DecisionTemplateService._row(
                    "intervention", t, counts[t.id], iv_cov.get(str(t.id))))

        if kind in ("", "national_proposal"):
            counts = {
                r["national_proposal_id"]: r["n"]
                for r in (CriterionEvidence.objects.filter(national_proposal__isnull=False)
                          .values("national_proposal_id")
                          .annotate(n=Count("criterion_id", distinct=True)))
            }
            for t in (NationalProgramProposal.objects.filter(id__in=counts)
                      .select_related("package", "phase")):
                rows.append(DecisionTemplateService._row(
                    "national_proposal", t, counts[t.id], np_cov.get(str(t.id))))

        return _ok({"count": len(rows), "targets": rows})


    @staticmethod
    def get_template(pk, request=None, can_regenerate=False):
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
    def scoring_template(pk, request=None):
        """Evidence for the PANEL SCORING detail page. Same target envelope as
        `get_template`, but each criterion's `evidence` is a LIST — one item per
        uploaded record, each carrying that record's own scalar data (via
        `_child`). No merged bag, no `children`, no `service_rows`. This is the
        un-zipped shape: two records under one criterion stay two items, never a
        `[95, 272]` field list. Kept separate from `_target` so the export /
        general grid and the overview list are untouched."""
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
        return _ok(DecisionTemplateService._scoring_target(kind, t, rule_by_crit, request))


    @staticmethod
    def detailed_info(pk, request=None):
        """Full evidence for one target — same EvidenceTarget shape as
        get_template, but nothing is trimmed. `target_fields` is the union of
        every field submitted (not just the rule's important subset) and each
        record's evidence is the raw `data` (empty values kept). This is the
        "everything the proposer submitted" view, not the cleaned summary."""
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
        field = "intervention" if kind == "intervention" else "national_proposal"
        ev_qs = (CriterionEvidence.objects.filter(**{field: t})
                 .select_related("criterion")
                 .order_by("criterion__criteria", "created_at", "id"))

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
                    # rule fields first, then every other submitted key appended below
                    "target_fields": list(rule.target_fields or []) if rule else [],
                    "evidence": {},   # merged view — raw, empties kept
                    "children": [],   # every record, raw data untouched
                    "guides": DecisionTemplateService._guides(rule, request),
                }
                groups[key] = g

            data = ev.data if isinstance(ev.data, dict) else {}
            for k in data.keys():
                if k not in g["target_fields"]:
                    g["target_fields"].append(k)
            for k, v in data.items():
                DecisionTemplateService._merge_raw(g["evidence"], k, v)
            g["children"].append({
                "evidence_id": str(ev.id),
                "score": getattr(ev, "score", None),
                "created_at": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
                "evidence": dict(data),  # RAW — nothing dropped, nothing merged
            })

        return _ok({
            "id": str(t.id),
            "reference_number": getattr(t, "reference_number", None),
            "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
            "kind": kind,
            "package": getattr(getattr(t, "package", None), "name", None),
            "phase": getattr(getattr(t, "phase", None), "name", None),
            "criteria": list(groups.values()),
        })

    @staticmethod
    def _merge_raw(bag, key, value):
        """Merge for the detailed view — unlike _add_field it does NOT drop
        empty values, so blank fields still surface. Distinct values on the
        same key collect into a list."""
        if key not in bag:
            bag[key] = value
            return
        cur = bag[key] if isinstance(bag[key], list) else [bag[key]]
        add = value if isinstance(value, list) else [value]
        bag[key] = cur + [x for x in add if x not in cur]

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
    def _assessment_coverage():
        """target-id -> assessment-evidence id, so the overview can link to the
        evidence detail ONLY for targets that have some. First evidence wins.
        (Assumes AssessmentEvidence M2M fields `interventions` /
        `program_proposals` — adjust the two accessors if yours differ.)"""
        from app.models import AssessmentEvidence
        iv, np = {}, {}
        for ev in (AssessmentEvidence.objects
                   .prefetch_related("interventions", "program_proposals")):
            eid = str(ev.id)
            for x in ev.interventions.all():
                iv.setdefault(str(x.id), eid)
            for x in ev.program_proposals.all():
                np.setdefault(str(x.id), eid)
        return iv, np

    @staticmethod
    def _assessment_for(kind, t):
        """Assessment-evidence id for one target (or None). Used on the detail
        envelope so it can link straight to the evidence detail when present."""
        from app.models import AssessmentEvidence
        field = "interventions" if kind == "intervention" else "program_proposals"
        ev = AssessmentEvidence.objects.filter(**{field: t}).order_by("id").first()
        return str(ev.id) if ev else None

    @staticmethod
    def _row(kind, t, criteria_count, assessment_evidence=None):
        row = {
            "id": str(t.id),
            "reference_number": getattr(t, "reference_number", None),
            "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
            "kind": kind,
            "package": getattr(getattr(t, "package", None), "name", None),
            "phase": getattr(getattr(t, "phase", None), "name", None),
            "criteria_count": criteria_count,
        }
        # only surfaced when the target actually has assessment evidence —
        # frontend links to its detail with this id.
        if assessment_evidence:
            row["assessment_evidence"] = assessment_evidence
        return row


    @staticmethod
    def _target(kind, t, rule_by_crit, request):
        field = "intervention" if kind == "intervention" else "national_proposal"
        ev_qs = (CriterionEvidence.objects.filter(**{field: t})
                 .select_related("criterion")
                 .order_by("criterion__criteria"))

        groups = {}
        # per-service rows for the general/export view. we DON'T merge or clean
        # here — each uploaded evidence record is kept as it was uploaded, then
        # grouped by its own service. so field values stay row-aligned and no
        # value zips across services (the "4 values" bug).
        service_buckets = {}
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
                    # merged view — every record for this criterion folded together.
                    # kept exactly as before so existing consumers are unaffected.
                    "evidence": {},
                    # one entry per evidence record, kept whole. lets criteria that
                    # carry more than one record (duplicates) be rendered individually
                    # instead of only as the merged bag above.
                    "children": [],
                    "guides": DecisionTemplateService._guides(rule, request),
                }
                groups[key] = g
            for f in (rule.target_fields or [] if rule else []):
                if f not in g["target_fields"]:
                    g["target_fields"].append(f)
            DecisionTemplateService._absorb(g["evidence"], ev)
            g["children"].append(DecisionTemplateService._child(ev))

            # bucket this record under its own service, kept RAW (exactly as
            # uploaded — no merge, no cleaning). first record for a given
            # service+criterion wins; duplicates stay visible via `children`.
            data = ev.data if isinstance(ev.data, dict) else {}
            skey, sdisp = DecisionTemplateService._service_of(data)
            sb = service_buckets.setdefault(
                skey, {"service": sdisp, "service_key": skey, "criteria": {}}
            )
            sb["criteria"].setdefault(key, dict(data))

        out = {
            "id": str(t.id),
            "reference_number": getattr(t, "reference_number", None),
            "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
            "kind": kind,
            "package": getattr(getattr(t, "package", None), "name", None),
            "phase": getattr(getattr(t, "phase", None), "name", None),
            "criteria": list(groups.values()),
            # raw evidence rows grouped by service for the general/export grid.
            # one entry per distinct service; `criteria` maps criterion-name
            # (lowercased, matching the frontend column key) -> that record's
            # raw uploaded data (empties kept).
            "service_rows": list(service_buckets.values()),
        }
        # only surfaced when the target actually has assessment evidence.
        ass = DecisionTemplateService._assessment_for(kind, t)
        if ass:
            out["assessment_evidence"] = ass
        return out


    @staticmethod
    def _scoring_target(kind, t, rule_by_crit, request):
        """Builder for `scoring_template`. Same envelope as `_target`, but each
        criterion's `evidence` is a LIST of whole records (scalar, un-zipped) —
        no merged bag, no `children`, no `service_rows`. `_child`/`_record` do
        the per-record cleaning, so nothing merges across records."""
        field = "intervention" if kind == "intervention" else "national_proposal"
        ev_qs = (CriterionEvidence.objects.filter(**{field: t})
                 .select_related("criterion")
                 .order_by("criterion__criteria", "created_at", "id"))

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
                    # ONE ITEM PER UPLOADED RECORD, in upload order. Each item is
                    # that record's own scalar data (empties dropped). Two records
                    # → two items, never `[95, 272]`.
                    "evidence": [],
                    "guides": DecisionTemplateService._guides(rule, request),
                }
                groups[key] = g
            for f in (rule.target_fields or [] if rule else []):
                if f not in g["target_fields"]:
                    g["target_fields"].append(f)
            g["evidence"].append(DecisionTemplateService._child(ev))

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
    def _service_of(data):
        """Normalized service for row-splitting. Returns (key, display).
        `key` is lowercase-alphanumeric only, so spelling/spacing variants
        collapse to one row (mirrors the frontend service-key normalization).
        Records with no service land under the "" key (the No-service row)."""
        v = data.get("service") if isinstance(data, dict) else None
        if isinstance(v, list):
            v = next((x for x in v if x not in (None, "")), "")
        v = v if isinstance(v, str) else ("" if v is None else str(v))
        disp = v.strip()
        key = "".join(ch for ch in disp.lower() if ch.isalnum())
        return key, disp


    @staticmethod
    def _absorb(bag, ev):
        data = ev.data if isinstance(ev.data, dict) else {}
        for k, v in data.items():
            DecisionTemplateService._add_field(bag, k, v)

    @staticmethod
    def _child(ev):
        """One evidence record, kept intact — the unit that lets duplicates render
        as separate children rather than collapsing into the merged bag."""
        return {
            "evidence_id": str(ev.id),
            "score": getattr(ev, "score", None),
            "created_at": ev.created_at.isoformat() if getattr(ev, "created_at", None) else None,
            "evidence": DecisionTemplateService._record(ev),
        }

    @staticmethod
    def _record(ev):
        """Non-empty fields of a single evidence row — same per-field cleaning as
        the merged bag, but for one record only (no cross-record list merging)."""
        bag = {}
        data = ev.data if isinstance(ev.data, dict) else {}
        for k, v in data.items():
            DecisionTemplateService._add_field(bag, k, v)
        return bag

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

    @classmethod
    def evidence_for_target(cls, target_type: str, target_id: str, request=None) -> dict:
        """
        One target's full evidence payload — the same EvidenceTarget the detail
        endpoint returns (criteria, each with target_fields, evidence, guides).
        Resolves the target, then delegates to the single-target builder (`_target`).
        """
        model = InterventionProposal if target_type == "intervention" else NationalProgramProposal
        t = (model.objects.filter(pk=target_id)
             .select_related("package", "phase").first())
        if not t:
            raise ValueError(f"{target_type} {target_id} not found")
        return cls._target(target_type, t, cls._rules(), request)