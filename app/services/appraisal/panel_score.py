# from app.models import (
#     PanelAppraisalScore, CriteriaAppraisalTool,
#     InterventionProposal, NationalProgramProposal,
# )
# from app.serializers import PanelAppraisalScoreSerializer


# def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
# def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
# def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()


# class PanelScoreService:

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
#     def _prepare(row):
#         criteria = _get_or_404(CriteriaAppraisalTool, row.get("criteria"))
#         if not criteria:
#             return None, None, "criteria not found"
#         target, err = PanelScoreService._resolve_target(row)
#         if err:
#             return None, None, err
#         return criteria, target, None

#     @staticmethod
#     def list_scores(params):
#         qs = (PanelAppraisalScore.objects
#               .select_related("criteria", "reviewer", "intervention", "national_proposal")
#               .order_by("-updated_at"))
#         for f in ("criteria", "intervention", "national_proposal", "reviewer"):
#             if v := params.get(f):
#                 qs = qs.filter(**{f: v})
#         if (svc := params.get("service")) is not None:
#             qs = qs.filter(service_key=PanelAppraisalScore.make_service_key(svc))
#         return _ok(PanelAppraisalScoreSerializer(qs, many=True).data)

#     @staticmethod
#     def get_score(pk):
#         obj = _get_or_404(PanelAppraisalScore, pk)
#         return _ok(PanelAppraisalScoreSerializer(obj).data) if obj else _err("not found", 404)

#     @staticmethod
#     def scores_summary(params):
#         """One row per scored unit (target + service): distinct reviewer count,
#         target/service/phase for display, and each reviewer's scores nested —
#         score id, criterion name, chosen option's scoring_approach, points, notes.

#         Two dates ride on each row so the client can group correctly:
#           submitted_at — the TARGET's own date (when the proposal was submitted).
#           scored_at    — the earliest score's created_at (when scoring happened).
#         The report groups by scored_at for full sessions (>6 criteria) and by
#         submitted_at otherwise; both are provided so that choice stays client-side."""
#         qs = (PanelAppraisalScore.objects
#               .select_related("intervention", "national_proposal",
#                               "intervention__phase", "national_proposal__phase",
#                               "intervention__package", "national_proposal__package",
#                               "criteria", "reviewer"))

#         for f in ("intervention", "national_proposal"):
#             if v := params.get(f):
#                 qs = qs.filter(**{f: v})
#         if (svc := params.get("service")) is not None and svc != "":
#             qs = qs.filter(service_key=PanelAppraisalScore.make_service_key(svc))

#         buckets = {}
#         for s in qs:
#             tid = s.national_proposal_id or s.intervention_id
#             if not tid:
#                 continue
#             key = (str(tid), s.service_key or "")
#             b = buckets.get(key)
#             if not b:
#                 target = s.national_proposal or s.intervention
#                 phase = getattr(target, "phase", None)
#                 pkg = getattr(target, "package", None)
#                 submitted = (getattr(target, "submitted_at", None)
#                              or getattr(target, "created_at", None))
#                 b = {
#                     "target_id": str(tid),
#                     "target_type": "national_proposal" if s.national_proposal_id else "intervention",
#                     "intervention": (getattr(target, "intervention_name", None)
#                                      or getattr(target, "title", None) or ""),
#                     "reference_number": getattr(target, "reference_number", None),
#                     # TARGET date (proposal submission). Client uses this for
#                     # partial units (<=6 criteria scored).
#                     "submitted_at": submitted.isoformat() if submitted else None,
#                     # SCORING date — filled after the loop from the earliest
#                     # score created_at. Client uses this for full sessions (>6).
#                     "scored_at": None,
#                     "service": s.service or "",
#                     "phase": getattr(phase, "name", None) if phase else None,
#                     "package": getattr(pkg, "name", None) if pkg else None,
#                     "_reviewers": set(),
#                     "_scored_times": [],
#                     "scores": [],
#                 }
#                 buckets[key] = b

#             b["_reviewers"].add(s.reviewer_id)
#             if s.created_at:
#                 b["_scored_times"].append(s.created_at)
#             crit = s.criteria  # the chosen CriteriaAppraisalTool option row
#             sc = s.score if isinstance(s.score, dict) else {}
#             b["scores"].append({
#                 "id": str(s.id),
#                 "reviewer_id": s.reviewer_id,
#                 "reviewer_name": getattr(s.reviewer, "username", ""),
#                 "criteria_id": str(s.criteria_id) if s.criteria_id else None,
#                 "criteria_name": getattr(crit, "criteria", "") if crit else "",
#                 "scoring_approach": getattr(crit, "scoring_approach", "") if crit else "",
#                 "score": sc.get("value"),
#                 "criteria_label": sc.get("criteria_label"),
#                 "comment": s.comment or "",
#                 "created_at": s.created_at.isoformat() if s.created_at else None,
#             })

#         rows = []
#         for b in buckets.values():
#             b["reviewers_scored"] = len(b.pop("_reviewers"))
#             times = b.pop("_scored_times")
#             earliest = min(times) if times else None
#             b["scored_at"] = earliest.isoformat() if earliest else None
#             rows.append(b)

#         if pkg := params.get("package"):
#             rows = [r for r in rows if r["package"] == pkg]
#         if ph := params.get("phase"):
#             rows = [r for r in rows if r["phase"] == ph]

#         rows.sort(key=lambda r: (r["intervention"] or "", r["service"] or ""))
#         return _ok({"count": len(rows), "rows": rows})

#     @staticmethod
#     def _upsert(row, reviewer):
#         """One record per (reviewer, target, criteria, service_key): update in
#         place, or create if absent. Duplicates across services survive because
#         service_key is part of the natural key."""
#         criteria, target, err = PanelScoreService._prepare(row)
#         if err:
#             return None, err
#         svc = row.get("service") or ""
#         obj, _ = PanelAppraisalScore.objects.update_or_create(
#             reviewer=reviewer, criteria=criteria, **target,
#             service_key=PanelAppraisalScore.make_service_key(svc),
#             defaults={
#                 "service": svc,
#                 "score": row.get("score") or {},
#                 "comment": row.get("comment") or "",
#             },
#         )
#         return obj, None

#     @staticmethod
#     def create_score(payload, reviewer):
#         obj, err = PanelScoreService._upsert(payload, reviewer)
#         return _err(err) if err else _ok(PanelAppraisalScoreSerializer(obj).data, 201)

#     @staticmethod
#     def update_score(pk, payload, reviewer, partial):
#         obj = _get_or_404(PanelAppraisalScore, pk)
#         if not obj:
#             return _err("not found", 404)
#         if "criteria" in payload and (c := _get_or_404(CriteriaAppraisalTool, payload["criteria"])):
#             obj.criteria = c
#         if "service" in payload:
#             obj.service = payload["service"] or ""
#         if "score" in payload:
#             obj.score = payload["score"] or {}
#         if "comment" in payload:
#             obj.comment = payload["comment"] or ""
#         obj.save()
#         return _ok(PanelAppraisalScoreSerializer(obj).data)

#     @staticmethod
#     def delete_score(pk):
#         obj = _get_or_404(PanelAppraisalScore, pk)
#         if not obj:
#             return _err("not found", 404)
#         obj.delete()
#         return _ok(status=204)

#     @staticmethod
#     def bulk_upsert(rows, reviewer):
#         if not isinstance(rows, list):
#             return _err("expected a list of rows")
#         created, failed = 0, []
#         for i, row in enumerate(rows):
#             obj, err = PanelScoreService._upsert(row, reviewer)
#             if err:
#                 failed.append({"row": i, "error": err})
#             else:
#                 created += 1
#         return _ok({"upserted": created, "failed": failed})

#     @staticmethod
#     def bulk_delete(ids):
#         if not isinstance(ids, list):
#             return _err("expected a list of ids")
#         n, _ = PanelAppraisalScore.objects.filter(id__in=ids).delete()
#         return _ok({"deleted": n})

#     @staticmethod
#     def delete_for_units(units):
#         """Delete every score row under the given scored units. Each unit is
#         {target_type, target_id, service}. Mirrors the report's unit grouping so
#         an admin can wipe a whole unit's scores in one call, without the client
#         having to enumerate individual score ids."""
#         if not isinstance(units, list):
#             return _err("expected a list of units")
#         from django.db.models import Q
#         q = Q()
#         touched = 0
#         for u in units:
#             tid = u.get("target_id")
#             if not tid:
#                 continue
#             ttype = u.get("target_type")
#             field = "national_proposal_id" if ttype == "national_proposal" else "intervention_id"
#             svc_key = PanelAppraisalScore.make_service_key(u.get("service") or "")
#             q |= Q(**{field: tid, "service_key": svc_key})
#             touched += 1
#         if not touched:
#             return _ok({"deleted": 0})
#         n, _ = PanelAppraisalScore.objects.filter(q).delete()
#         return _ok({"deleted": n})

from django.core.exceptions import ValidationError

from app.models import (
    PanelAppraisalScore, CriteriaAppraisalTool,
    InterventionProposal, NationalProgramProposal,
)
from app.serializers import PanelAppraisalScoreSerializer


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}


def _get_or_404(model, pk):
    # Robust to empty / malformed pks (e.g. a stray "" criteria from a
    # comment-only draft). A bad pk resolves to None instead of raising a
    # ValueError/ValidationError that would 500 a whole bulk batch.
    if pk in (None, "", b""):
        return None
    try:
        return model.objects.filter(pk=pk).first()
    except (ValueError, TypeError, ValidationError):
        return None


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
        # An empty/absent criteria means no option was selected — never create a
        # ghost row for it (that's the case that made a partial scope look
        # "complete" and lock).
        if not row.get("criteria"):
            return None, None, "criteria required"
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
    def scores_summary(params):
        """One row per scored unit (target + service): distinct reviewer count,
        target/service/phase for display, and each reviewer's scores nested —
        score id, criterion name, chosen option's scoring_approach, points, notes.

        Two dates ride on each row so the client can group correctly:
          submitted_at — the TARGET's own date (when the proposal was submitted).
          scored_at    — the earliest score's created_at (when scoring happened).
        The report groups by scored_at for full sessions (>6 criteria) and by
        submitted_at otherwise; both are provided so that choice stays client-side."""
        qs = (PanelAppraisalScore.objects
              .select_related("intervention", "national_proposal",
                              "intervention__phase", "national_proposal__phase",
                              "intervention__package", "national_proposal__package",
                              "criteria", "reviewer"))

        for f in ("intervention", "national_proposal"):
            if v := params.get(f):
                qs = qs.filter(**{f: v})
        if (svc := params.get("service")) is not None and svc != "":
            qs = qs.filter(service_key=PanelAppraisalScore.make_service_key(svc))

        buckets = {}
        for s in qs:
            tid = s.national_proposal_id or s.intervention_id
            if not tid:
                continue
            key = (str(tid), s.service_key or "")
            b = buckets.get(key)
            if not b:
                target = s.national_proposal or s.intervention
                phase = getattr(target, "phase", None)
                pkg = getattr(target, "package", None)
                submitted = (getattr(target, "submitted_at", None)
                             or getattr(target, "created_at", None))
                b = {
                    "target_id": str(tid),
                    "target_type": "national_proposal" if s.national_proposal_id else "intervention",
                    "intervention": (getattr(target, "intervention_name", None)
                                     or getattr(target, "title", None) or ""),
                    "reference_number": getattr(target, "reference_number", None),
                    # TARGET date (proposal submission). Client uses this for
                    # partial units (<=6 criteria scored).
                    "submitted_at": submitted.isoformat() if submitted else None,
                    # SCORING date — filled after the loop from the earliest
                    # score created_at. Client uses this for full sessions (>6).
                    "scored_at": None,
                    "service": s.service or "",
                    "phase": getattr(phase, "name", None) if phase else None,
                    "package": getattr(pkg, "name", None) if pkg else None,
                    "_reviewers": set(),
                    "_scored_times": [],
                    "scores": [],
                }
                buckets[key] = b

            b["_reviewers"].add(s.reviewer_id)
            if s.created_at:
                b["_scored_times"].append(s.created_at)
            crit = s.criteria  # the chosen CriteriaAppraisalTool option row
            sc = s.score if isinstance(s.score, dict) else {}
            b["scores"].append({
                "id": str(s.id),
                "reviewer_id": s.reviewer_id,
                "reviewer_name": getattr(s.reviewer, "username", ""),
                "criteria_id": str(s.criteria_id) if s.criteria_id else None,
                "criteria_name": getattr(crit, "criteria", "") if crit else "",
                "scoring_approach": getattr(crit, "scoring_approach", "") if crit else "",
                "score": sc.get("value"),
                "criteria_label": sc.get("criteria_label"),
                "comment": s.comment or "",
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })

        rows = []
        for b in buckets.values():
            b["reviewers_scored"] = len(b.pop("_reviewers"))
            times = b.pop("_scored_times")
            earliest = min(times) if times else None
            b["scored_at"] = earliest.isoformat() if earliest else None
            rows.append(b)

        if pkg := params.get("package"):
            rows = [r for r in rows if r["package"] == pkg]
        if ph := params.get("phase"):
            rows = [r for r in rows if r["phase"] == ph]

        rows.sort(key=lambda r: (r["intervention"] or "", r["service"] or ""))
        return _ok({"count": len(rows), "rows": rows})

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
            try:
                obj, err = PanelScoreService._upsert(row, reviewer)
            except Exception as e:  # one bad row must never 500 the whole batch
                err, obj = str(e), None
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

    @staticmethod
    def delete_for_units(units):
        """Delete every score row under the given scored units. Each unit is
        {target_type, target_id, service}. Mirrors the report's unit grouping so
        an admin can wipe a whole unit's scores in one call, without the client
        having to enumerate individual score ids."""
        if not isinstance(units, list):
            return _err("expected a list of units")
        from django.db.models import Q
        q = Q()
        touched = 0
        for u in units:
            tid = u.get("target_id")
            if not tid:
                continue
            ttype = u.get("target_type")
            field = "national_proposal_id" if ttype == "national_proposal" else "intervention_id"
            svc_key = PanelAppraisalScore.make_service_key(u.get("service") or "")
            q |= Q(**{field: tid, "service_key": svc_key})
            touched += 1
        if not touched:
            return _ok({"deleted": 0})
        n, _ = PanelAppraisalScore.objects.filter(q).delete()
        return _ok({"deleted": n})