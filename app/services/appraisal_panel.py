# from django.db import IntegrityError

# from app.models import CriteriaAppraisalTool, CriterionEvidence, InterventionProposal, NationalProgramProposal
# from app.serializers import CriteriaAppraisalToolSerializer, CriterionEvidenceSerializer


# def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
# def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
# def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


# class AppraisalPanelService:

#     @staticmethod
#     def _validate_headers(headers):
#         if headers in (None, []):         return None
#         if not isinstance(headers, list): return "headers must be a list"
#         for h in headers:
#             if not isinstance(h, dict) or not h.get("key") or not h.get("label"):
#                 return "each header needs key + label"
#         return None

#     @staticmethod
#     def _validate_evidence_data(criterion, data):
#         allowed = {h.get("key") for h in (criterion.headers or []) if h.get("key")}
#         if not allowed:                   return None          # no schema declared → accept
#         unknown = set(data or {}) - allowed
#         return f"unknown keys: {', '.join(sorted(unknown))}" if unknown else None

#     @staticmethod
#     def _resolve_target(row):
#         iv, npr = row.get("intervention"), row.get("national_proposal")
#         if bool(iv) == bool(npr):
#             return None, "exactly one of intervention / national_proposal required"
#         if iv:
#             obj = _get_or_404(InterventionProposal, iv)
#             return ({"intervention": obj}, None) if obj else (None, "intervention not found")
#         obj = _get_or_404(NationalProgramProposal, npr)
#         return ({"national_proposal": obj}, None) if obj else (None, "national_proposal not found")

#     @staticmethod
#     def list_criteria(params):
#         qs = CriteriaAppraisalTool.objects.all().order_by("criteria")
#         active = params.get("active")
#         if active is not None:
#             qs = qs.filter(active=str(active).lower() in ("1", "true", "yes"))
#         return _ok(CriteriaAppraisalToolSerializer(qs, many=True).data)

#     @staticmethod
#     def get_criterion(pk):
#         obj = _get_or_404(CriteriaAppraisalTool, pk)
#         return _ok(CriteriaAppraisalToolSerializer(obj).data) if obj else _err("not found", 404)

#     @staticmethod
#     def create_criterion(payload):
#         if err := AppraisalPanelService._validate_headers(payload.get("headers")):
#             return _err(err)
#         s = CriteriaAppraisalToolSerializer(data=payload)
#         if not s.is_valid(): return _err(s.errors)
#         s.save()
#         return _ok(s.data, 201)

#     @staticmethod
#     def update_criterion(pk, payload, partial):
#         obj = _get_or_404(CriteriaAppraisalTool, pk)
#         if not obj: return _err("not found", 404)
#         if "headers" in payload and (err := AppraisalPanelService._validate_headers(payload.get("headers"))):
#             return _err(err)
#         s = CriteriaAppraisalToolSerializer(obj, data=payload, partial=partial)
#         if not s.is_valid(): return _err(s.errors)
#         # s.save()
#         # return _ok(s.data)
#         s.save()
#         if "headers" in payload:  # configure_criterion: `if "headers" in clean:`
#             AppraisalPanelService._recompute_criterion(s.instance)
#         return _ok(s.data)

#     @staticmethod
#     def configure_criterion(pk, payload):
#         """Panel-only: whitelists the fields the panel page controls."""
#         obj = _get_or_404(CriteriaAppraisalTool, pk)
#         if not obj: return _err("not found", 404)
#         allowed = {"headers", "active", "scoring_approach", "score", "description"}
#         clean = {k: v for k, v in payload.items() if k in allowed}
#         if "headers" in clean and (err := AppraisalPanelService._validate_headers(clean["headers"])):
#             return _err(err)
#         s = CriteriaAppraisalToolSerializer(obj, data=clean, partial=True)
#         if not s.is_valid(): return _err(s.errors)
#         # s.save()
#         # return _ok(s.data)
#         s.save()
#         if "headers" in payload:  # configure_criterion: `if "headers" in clean:`
#             AppraisalPanelService._recompute_criterion(s.instance)
#         return _ok(s.data)

#     @staticmethod
#     def delete_criterion(pk):
#         obj = _get_or_404(CriteriaAppraisalTool, pk)
#         if not obj: return _err("not found", 404)
#         if obj.evidence.exists(): return _err("criterion has evidence; cannot delete", 409)
#         obj.delete()
#         return _ok(status=204)

#     @staticmethod
#     def list_evidence(params):
#         qs = CriterionEvidence.objects.select_related("criterion").order_by("-updated_at")
#         for f in ("criterion", "intervention", "national_proposal"):
#             if v := params.get(f): qs = qs.filter(**{f: v})
#         return _ok(CriterionEvidenceSerializer(qs, many=True).data)

#     @staticmethod
#     def _prepare_evidence(row):
#         """Shared validation for both upsert and insert paths."""
#         criterion = _get_or_404(CriteriaAppraisalTool, row.get("criterion"))
#         if not criterion: return None, None, "criterion not found"
#         target, err = AppraisalPanelService._resolve_target(row)
#         if err: return None, None, err
#         if err := AppraisalPanelService._validate_evidence_data(criterion, row.get("data") or {}):
#             return None, None, err
#         return criterion, target, None

#     @staticmethod
#     def _upsert_evidence(row):
#         """One record per (criterion, target): update in place, or create if absent."""
#         criterion, target, err = AppraisalPanelService._prepare_evidence(row)
#         if err: return None, err
#         obj, _ = CriterionEvidence.objects.update_or_create(
#             criterion=criterion, **target,
#             defaults={"data": row.get("data") or {}, "score": row.get("score")},
#         )
#         return obj, None

#     @staticmethod
#     def _insert_evidence(row):
#         """Always create a fresh record — used when a target genuinely has more
#         records in the file than exist in the database yet."""
#         criterion, target, err = AppraisalPanelService._prepare_evidence(row)
#         if err: return None, err
#         try:
#             obj = CriterionEvidence.objects.create(
#                 criterion=criterion, **target,
#                 data=row.get("data") or {}, score=row.get("score"),
#             )
#         except IntegrityError:
#             return None, ("duplicate blocked by a unique constraint on (criterion, target); "
#                           "drop it via migration to allow duplicate evidence rows")
#         return obj, None

#     @staticmethod
#     def _update_record(obj, row):
#         """Overwrite an existing record's data in place. Score is only touched
#         when the row carries one, so panel-set scores aren't wiped on re-upload."""
#         if err := AppraisalPanelService._validate_evidence_data(obj.criterion, row.get("data") or {}):
#             return None, err
#         obj.data = row.get("data") or {}
#         if "score" in row:
#             obj.score = row.get("score")
#         obj.save()
#         return obj, None

#     # @staticmethod
#     # def create_evidence(payload):
#     #     obj, err = AppraisalPanelService._upsert_evidence(payload)
#     #     return _err(err) if err else _ok(CriterionEvidenceSerializer(obj).data, 201)

#     # @staticmethod
#     # def update_evidence(pk, payload, partial):
#     #     obj = _get_or_404(CriterionEvidence, pk)
#     #     if not obj: return _err("not found", 404)
#     #     if "data" in payload and (err := AppraisalPanelService._validate_evidence_data(obj.criterion, payload["data"])):
#     #         return _err(err)
#     #     s = CriterionEvidenceSerializer(obj, data=payload, partial=partial)
#     #     if not s.is_valid(): return _err(s.errors)
#     #     s.save()
#         # return _ok(s.data)
#     @staticmethod
#     def create_evidence(payload):
#         obj, err = AppraisalPanelService._upsert_evidence(payload)
#         if err:
#             return _err(err)
#         AppraisalPanelService._recompute_target(
#             intervention_id=obj.intervention_id,
#             national_proposal_id=obj.national_proposal_id)
#         obj.refresh_from_db()
#         return _ok(CriterionEvidenceSerializer(obj).data, 201)

#     @staticmethod
#     def update_evidence(pk, payload, partial):
#         obj = _get_or_404(CriterionEvidence, pk)
#         if not obj: return _err("not found", 404)
#         if "data" in payload and (err := AppraisalPanelService._validate_evidence_data(obj.criterion, payload["data"])):
#             return _err(err)
#         s = CriterionEvidenceSerializer(obj, data=payload, partial=partial)
#         if not s.is_valid(): return _err(s.errors)
#         s.save()
#         AppraisalPanelService._recompute_target(
#             intervention_id=obj.intervention_id,
#             national_proposal_id=obj.national_proposal_id)
#         obj.refresh_from_db()
#         return _ok(CriterionEvidenceSerializer(obj).data)

#     @staticmethod
#     def delete_evidence(pk):
#         obj = _get_or_404(CriterionEvidence, pk)
#         if not obj: return _err("not found", 404)
#         obj.delete()
#         return _ok(status=204)

#     @staticmethod
#     def bulk_upload_evidence(rows):
#         if not isinstance(rows, list): return _err("expected a list of rows")

#         # group incoming rows by (criterion, target), preserving the file's order
#         groups = {}
#         for i, row in enumerate(rows):
#             key = (row.get("criterion"), row.get("intervention"), row.get("national_proposal"))
#             groups.setdefault(key, []).append((i, row))

#         created, updated, failed = 0, 0, []
#         for (crit_id, iv, npr), items in groups.items():
#             # existing records for this exact target, in a stable order so the
#             # k-th uploaded row always lines up with the same k-th record.
#             existing = list(
#                 CriterionEvidence.objects
#                 .filter(criterion_id=crit_id, intervention_id=iv, national_proposal_id=npr)
#                 .order_by("created_at", "id")
#             )
#             for pos, (i, row) in enumerate(items):
#                 if pos < len(existing):
#                     # reconcile in place — re-uploading the same file updates,
#                     # it does not pile on new duplicates
#                     _, err = AppraisalPanelService._update_record(existing[pos], row)
#                     if err: failed.append({"row": i, "error": err})
#                     else: updated += 1
#                 else:
#                     # file has more records for this target than exist → add them
#                     _, err = AppraisalPanelService._insert_evidence(row)
#                     if err: failed.append({"row": i, "error": err})
#                     else: created += 1
#         # return _ok({"created": created, "updated": updated, "failed": failed})
#         # recompute formula fields for every target this upload touched
#         for iv, npr in {(g[1], g[2]) for g in groups.keys()}:
#             AppraisalPanelService._recompute_target(intervention_id=iv, national_proposal_id=npr)

#         return _ok({"created": created, "updated": updated, "failed": failed})

#     @staticmethod
#     def bulk_delete_evidence(ids):
#         if not isinstance(ids, list): return _err("expected a list of ids")
#         n, _ = CriterionEvidence.objects.filter(id__in=ids).delete()
#         return _ok({"deleted": n})
    
    
#     @staticmethod
#     def _recompute_target(*, intervention_id=None, national_proposal_id=None, max_passes=8):
#         """Recompute every formula field for all of a target's rows, iterated to
#         a fixpoint so cross-criterion chains settle. Persists only changed rows."""
#         from app.services.appraisal.formulas import compute_row, _num  
#         flt = {}
#         if intervention_id is not None:      flt["intervention_id"] = intervention_id
#         if national_proposal_id is not None: flt["national_proposal_id"] = national_proposal_id
#         if not flt:
#             return []

#         rows = list(
#             CriterionEvidence.objects.filter(**flt)
#             .select_related("criterion").order_by("created_at", "id")
#         )
#         work = [r for r in rows
#                 if any((h or {}).get("formula") for h in (r.criterion.headers or []))]
#         if not work:
#             return []

#         # oldest row per criterion name is the representative for cross-criterion refs
#         rep = {}
#         for r in rows:
#             rep.setdefault((r.criterion.criteria or "").strip().lower(), r)

#         def ref(name, key, default=0):
#             r = rep.get(str(name).strip().lower())
#             if not r:
#                 return float(default)
#             v = (r.data or {}).get(key)
#             if v in (None, ""):
#                 return float(default)
#             try:
#                 return _num(v)
#             except Exception:  # noqa: BLE001
#                 return float(default)

#         original = {r.id: dict(r.data or {}) for r in work}
#         for _ in range(max_passes):
#             changed = False
#             for r in work:
#                 new_data, _err = compute_row(r.criterion.headers or [], r.data or {}, ref)
#                 if new_data != (r.data or {}):
#                     r.data = new_data
#                     changed = True
#             if not changed:
#                 break

#         saved = []
#         for r in work:
#             if (r.data or {}) != original.get(r.id, {}):
#                 r.save(update_fields=["data", "updated_at"])
#                 saved.append(str(r.id))
#         return saved

#     @staticmethod
#     def _recompute_criterion(criterion):
#         if not any((h or {}).get("formula") for h in (criterion.headers or [])):
#             return []
#         pairs = (CriterionEvidence.objects.filter(criterion=criterion)
#                  .values_list("intervention_id", "national_proposal_id").distinct())
#         touched = []
#         for iv, npr in pairs:
#             touched += AppraisalPanelService._recompute_target(
#                 intervention_id=iv, national_proposal_id=npr)
#         return touched

#     @staticmethod
#     def recompute(payload):
#         crit = payload.get("criterion")
#         if crit:
#             obj = _get_or_404(CriteriaAppraisalTool, crit)
#             if not obj:
#                 return _err("criterion not found", 404)
#             return _ok({"recomputed": AppraisalPanelService._recompute_criterion(obj)})
#         iv, npr = payload.get("intervention"), payload.get("national_proposal")
#         if iv or npr:
#             return _ok({"recomputed": AppraisalPanelService._recompute_target(
#                 intervention_id=iv, national_proposal_id=npr)})
#         return _err("provide criterion or a target")


from django.db import IntegrityError

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
        # s.save()
        # return _ok(s.data)
        s.save()
        if "headers" in payload:  # configure_criterion: `if "headers" in clean:`
            AppraisalPanelService._recompute_criterion(s.instance)
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
        # s.save()
        # return _ok(s.data)
        s.save()
        if "headers" in payload:  # configure_criterion: `if "headers" in clean:`
            AppraisalPanelService._recompute_criterion(s.instance)
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
    def _prepare_evidence(row):
        """Shared validation for both upsert and insert paths."""
        criterion = _get_or_404(CriteriaAppraisalTool, row.get("criterion"))
        if not criterion: return None, None, "criterion not found"
        target, err = AppraisalPanelService._resolve_target(row)
        if err: return None, None, err
        if err := AppraisalPanelService._validate_evidence_data(criterion, row.get("data") or {}):
            return None, None, err
        return criterion, target, None

    @staticmethod
    def _upsert_evidence(row):
        """One record per (criterion, target): update in place, or create if absent."""
        criterion, target, err = AppraisalPanelService._prepare_evidence(row)
        if err: return None, err
        obj, _ = CriterionEvidence.objects.update_or_create(
            criterion=criterion, **target,
            defaults={"data": row.get("data") or {}, "score": row.get("score")},
        )
        return obj, None

    @staticmethod
    def _insert_evidence(row):
        """Always create a fresh record — used when a target genuinely has more
        records in the file than exist in the database yet."""
        criterion, target, err = AppraisalPanelService._prepare_evidence(row)
        if err: return None, err
        try:
            obj = CriterionEvidence.objects.create(
                criterion=criterion, **target,
                data=row.get("data") or {}, score=row.get("score"),
            )
        except IntegrityError:
            return None, ("duplicate blocked by a unique constraint on (criterion, target); "
                          "drop it via migration to allow duplicate evidence rows")
        return obj, None

    @staticmethod
    def _update_record(obj, row):
        """Overwrite an existing record's data in place. Score is only touched
        when the row carries one, so panel-set scores aren't wiped on re-upload."""
        if err := AppraisalPanelService._validate_evidence_data(obj.criterion, row.get("data") or {}):
            return None, err
        obj.data = row.get("data") or {}
        if "score" in row:
            obj.score = row.get("score")
        obj.save()
        return obj, None

    # @staticmethod
    # def create_evidence(payload):
    #     obj, err = AppraisalPanelService._upsert_evidence(payload)
    #     return _err(err) if err else _ok(CriterionEvidenceSerializer(obj).data, 201)

    # @staticmethod
    # def update_evidence(pk, payload, partial):
    #     obj = _get_or_404(CriterionEvidence, pk)
    #     if not obj: return _err("not found", 404)
    #     if "data" in payload and (err := AppraisalPanelService._validate_evidence_data(obj.criterion, payload["data"])):
    #         return _err(err)
    #     s = CriterionEvidenceSerializer(obj, data=payload, partial=partial)
    #     if not s.is_valid(): return _err(s.errors)
    #     s.save()
        # return _ok(s.data)
    @staticmethod
    def create_evidence(payload):
        obj, err = AppraisalPanelService._upsert_evidence(payload)
        if err:
            return _err(err)
        AppraisalPanelService._recompute_target(
            intervention_id=obj.intervention_id,
            national_proposal_id=obj.national_proposal_id)
        obj.refresh_from_db()
        return _ok(CriterionEvidenceSerializer(obj).data, 201)

    @staticmethod
    def update_evidence(pk, payload, partial):
        obj = _get_or_404(CriterionEvidence, pk)
        if not obj: return _err("not found", 404)
        if "data" in payload and (err := AppraisalPanelService._validate_evidence_data(obj.criterion, payload["data"])):
            return _err(err)
        s = CriterionEvidenceSerializer(obj, data=payload, partial=partial)
        if not s.is_valid(): return _err(s.errors)
        s.save()
        AppraisalPanelService._recompute_target(
            intervention_id=obj.intervention_id,
            national_proposal_id=obj.national_proposal_id)
        obj.refresh_from_db()
        return _ok(CriterionEvidenceSerializer(obj).data)

    @staticmethod
    def delete_evidence(pk):
        obj = _get_or_404(CriterionEvidence, pk)
        if not obj: return _err("not found", 404)
        obj.delete()
        return _ok(status=204)

    @staticmethod
    def bulk_upload_evidence(rows):
        if not isinstance(rows, list): return _err("expected a list of rows")

        # group incoming rows by (criterion, target), preserving the file's order
        groups = {}
        for i, row in enumerate(rows):
            key = (row.get("criterion"), row.get("intervention"), row.get("national_proposal"))
            groups.setdefault(key, []).append((i, row))

        created, updated, failed = 0, 0, []
        for (crit_id, iv, npr), items in groups.items():
            # existing records for this exact target, in a stable order so the
            # k-th uploaded row always lines up with the same k-th record.
            existing = list(
                CriterionEvidence.objects
                .filter(criterion_id=crit_id, intervention_id=iv, national_proposal_id=npr)
                .order_by("created_at", "id")
            )
            for pos, (i, row) in enumerate(items):
                if pos < len(existing):
                    # reconcile in place — re-uploading the same file updates,
                    # it does not pile on new duplicates
                    _, err = AppraisalPanelService._update_record(existing[pos], row)
                    if err: failed.append({"row": i, "error": err})
                    else: updated += 1
                else:
                    # file has more records for this target than exist → add them
                    _, err = AppraisalPanelService._insert_evidence(row)
                    if err: failed.append({"row": i, "error": err})
                    else: created += 1
        # return _ok({"created": created, "updated": updated, "failed": failed})
        # recompute formula fields for every target this upload touched
        for iv, npr in {(g[1], g[2]) for g in groups.keys()}:
            AppraisalPanelService._recompute_target(intervention_id=iv, national_proposal_id=npr)

        return _ok({"created": created, "updated": updated, "failed": failed})

    @staticmethod
    def bulk_delete_evidence(ids):
        if not isinstance(ids, list): return _err("expected a list of ids")
        n, _ = CriterionEvidence.objects.filter(id__in=ids).delete()
        return _ok({"deleted": n})

    @staticmethod
    def _service_of(row):
        """The service value on a row, read from its criterion's service/services
        column. Returns a lower-cased service label, or None when the criterion
        has no service column or the value is blank — those rows resolve at the
        target level (e.g. a single Burden-of-Disease record informing every
        service), not per service."""
        keys = {
            (h.get("key") or "").strip().lower()
            for h in (row.criterion.headers or []) if isinstance(h, dict)
        }
        col = "service" if "service" in keys else ("services" if "services" in keys else None)
        if not col:
            return None
        v = (row.data or {}).get(col)
        s = str(v).strip() if v is not None else ""
        return s.lower() or None

    @staticmethod
    def _recompute_target(*, intervention_id=None, national_proposal_id=None, max_passes=8):
        """Recompute every formula field for all of a target's rows, iterated to
        a fixpoint so cross-criterion chains settle. Persists only changed rows.

        Cross-criterion ref() resolves within the SAME service where the
        referenced criterion is service-bearing; otherwise it falls back to the
        target-level representative (e.g. a single Burden-of-Disease record that
        informs every service)."""
        from app.services.appraisal.formulas import compute_row, _num
        flt = {}
        if intervention_id is not None:      flt["intervention_id"] = intervention_id
        if national_proposal_id is not None: flt["national_proposal_id"] = national_proposal_id
        if not flt:
            return []

        rows = list(
            CriterionEvidence.objects.filter(**flt)
            .select_related("criterion").order_by("created_at", "id")
        )
        work = [r for r in rows
                if any((h or {}).get("formula") for h in (r.criterion.headers or []))]
        if not work:
            return []

        # criterion-name -> { service(lower)|None : representative row }.
        # oldest row wins per (name, service); the None bucket is the
        # target-level fallback used when the reference isn't service-bearing
        # or has no record for the current row's service.
        rep = {}
        for r in rows:
            name = (r.criterion.criteria or "").strip().lower()
            svc = AppraisalPanelService._service_of(r)
            bucket = rep.setdefault(name, {})
            bucket.setdefault(svc, r)
            bucket.setdefault(None, r)

        def make_ref(current_service):
            def ref(name, key, default=0):
                bucket = rep.get(str(name).strip().lower())
                if not bucket:
                    return float(default)
                # same-service record first, then target-level fallback
                r = bucket.get(current_service) or bucket.get(None)
                if not r:
                    return float(default)
                v = (r.data or {}).get(key)
                if v in (None, ""):
                    return float(default)
                try:
                    return _num(v)
                except Exception:  # noqa: BLE001
                    return float(default)
            return ref

        original = {r.id: dict(r.data or {}) for r in work}
        for _ in range(max_passes):
            changed = False
            for r in work:
                svc = AppraisalPanelService._service_of(r)
                new_data, _err = compute_row(r.criterion.headers or [], r.data or {}, make_ref(svc))
                if new_data != (r.data or {}):
                    r.data = new_data
                    changed = True
            if not changed:
                break

        saved = []
        for r in work:
            if (r.data or {}) != original.get(r.id, {}):
                r.save(update_fields=["data", "updated_at"])
                saved.append(str(r.id))
        return saved

    @staticmethod
    def _recompute_criterion(criterion):
        if not any((h or {}).get("formula") for h in (criterion.headers or [])):
            return []
        pairs = (CriterionEvidence.objects.filter(criterion=criterion)
                 .values_list("intervention_id", "national_proposal_id").distinct())
        touched = []
        for iv, npr in pairs:
            touched += AppraisalPanelService._recompute_target(
                intervention_id=iv, national_proposal_id=npr)
        return touched

    @staticmethod
    def recompute(payload):
        crit = payload.get("criterion")
        if crit:
            obj = _get_or_404(CriteriaAppraisalTool, crit)
            if not obj:
                return _err("criterion not found", 404)
            return _ok({"recomputed": AppraisalPanelService._recompute_criterion(obj)})
        iv, npr = payload.get("intervention"), payload.get("national_proposal")
        if iv or npr:
            return _ok({"recomputed": AppraisalPanelService._recompute_target(
                intervention_id=iv, national_proposal_id=npr)})
        return _err("provide criterion or a target")