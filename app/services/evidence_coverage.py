from app.models import (
    CriteriaAppraisalTool, CriterionEvidence,
    InterventionProposal, NationalProgramProposal,
)


def _ok(data=None, status=200):  return {"ok": True,  "data": data, "status": status}
def _err(msg, status=400):       return {"ok": False, "error": msg, "status": status}
def _get_or_404(model, pk):      return model.objects.filter(pk=pk).first()

EMPTY_THRESHOLD = 0.075  


def _crit_key(name):
    """Normalise a criterion name so bands with the same name group together."""
    return (name or "").strip().lower()


class EvidenceCoverageService:

    # ── group the 5 tool rows into distinct criteria (by name) ──
    @staticmethod
    def _grouped_criteria():
        """
        Returns:
          groups: [{key, name, ids: [tool_id...], header_keys: [...]}]  one per distinct name
          id_to_key: {tool_id: group_key}  maps any band row to its group
        """
        groups = {}
        id_to_key = {}
        for c in CriteriaAppraisalTool.objects.filter(active=True).order_by("criteria"):
            key = _crit_key(c.criteria)
            id_to_key[c.id] = key
            g = groups.get(key)
            if not g:
                groups[key] = {
                    "key": key,
                    "name": c.criteria.strip(),
                    "ids": [c.id],
                    # headers come from whichever band declares them
                    "header_keys": [h.get("key") for h in (c.headers or []) if h.get("key")],
                    "headers": c.headers or [],
                }
            else:
                g["ids"].append(c.id)
                if not g["header_keys"] and c.headers:
                    g["header_keys"] = [h.get("key") for h in c.headers if h.get("key")]
                    g["headers"] = c.headers
        return list(groups.values()), id_to_key

    # ── completeness of one evidence row against the group's schema ──
    @staticmethod
    def _grade(evidence, header_keys):
        if evidence is None:
            return "missing", 0, len(header_keys)
        if not header_keys:
            has_any = bool(evidence.data)
            return ("complete" if has_any else "empty"), (1 if has_any else 0), 1

        data = evidence.data or {}
        filled = sum(1 for k in header_keys if not _is_blank(data.get(k)))
        total = len(header_keys)
        blank_ratio = 1 - (filled / total)

        if filled == 0 or blank_ratio > EMPTY_THRESHOLD:
            status = "empty"
        elif filled < total:
            status = "incomplete"
        else:
            status = "complete"
        return status, filled, total

    # ── overview: only targets present in CriterionEvidence ──────
    @staticmethod
    def list_coverage(params):
        groups, id_to_key = EvidenceCoverageService._grouped_criteria()

        # index evidence by (target_id, group_key) — collapse bands to one cell
        ev_map = {}
        intervention_ids = set()
        national_ids = set()
        for e in CriterionEvidence.objects.all().only(
            "id", "criterion_id", "intervention_id", "national_proposal_id", "data"
        ):
            gkey = id_to_key.get(e.criterion_id)
            if gkey is None:
                continue   # evidence for an inactive/removed criterion band
            tid = e.intervention_id or e.national_proposal_id
            # if two bands somehow both hold evidence for this target, keep the fuller one
            existing = ev_map.get((str(tid), gkey))
            if existing is None or len(e.data or {}) > len(existing.data or {}):
                ev_map[(str(tid), gkey)] = e
            if e.intervention_id:
                intervention_ids.add(e.intervention_id)
            elif e.national_proposal_id:
                national_ids.add(e.national_proposal_id)

        rows = []
        if intervention_ids:
            rows += EvidenceCoverageService._targets_of(
                InterventionProposal.objects
                    .filter(id__in=intervention_ids)
                    .select_related("package", "phase"),
                "intervention", groups, ev_map,
            )
        if national_ids:
            rows += EvidenceCoverageService._targets_of(
                NationalProgramProposal.objects
                    .filter(id__in=national_ids)
                    .select_related("package", "phase"),
                "national_proposal", groups, ev_map,
            )

        status = params.get("status")
        if status:
            rows = [r for r in rows if r["overall"] == status]

        return _ok({
            "criteria": [{"key": g["key"], "name": g["name"]} for g in groups],
            "targets": rows,
            "summary": EvidenceCoverageService._summarize(rows),
        })

    @staticmethod
    def _targets_of(queryset, kind, groups, ev_map):
        out = []
        for t in queryset:
            ref = getattr(t, "reference_number", None)
            name = (
                getattr(t, "intervention_name", None)
                or getattr(t, "title", None)
                or ref
            )
            per_criterion = []
            counts = {"complete": 0, "incomplete": 0, "empty": 0, "missing": 0}
            for g in groups:
                ev = ev_map.get((str(t.id), g["key"]))
                status, filled, total = EvidenceCoverageService._grade(ev, g["header_keys"])
                counts[status] += 1
                per_criterion.append({
                    "criterion": g["key"],
                    "criterion_id": str(g["ids"][0]), 
                    "criterion_name": g["name"],
                    "evidence_id": str(ev.id) if ev else None,
                    "status": status,
                    "filled": filled,
                    "total": total,
                })

            total_c = len(groups) or 1
            covered = total_c - counts["missing"]
            out.append({
                "id": str(t.id),
                "kind": kind,
                "reference_number": ref,
                "name": name,
                "package_name": getattr(getattr(t, "package", None), "name", None),
                "phase_name": getattr(getattr(t, "phase", None), "name", None),
                "coverage": {
                    "covered": covered,
                    "total": total_c,
                    "percent": round(covered / total_c * 100),
                },
                "counts": counts,
                "overall": EvidenceCoverageService._overall(counts, total_c),
                "criteria": per_criterion,
            })
        return out

    @staticmethod
    def _overall(counts, total):
        if counts["missing"] == total:
            return "missing"
        if counts["missing"] or counts["empty"]:
            return "incomplete"
        if counts["incomplete"]:
            return "partial"
        return "complete"

    @staticmethod
    def _summarize(rows):
        s = {"complete": 0, "partial": 0, "incomplete": 0, "missing": 0, "total": len(rows)}
        for r in rows:
            s[r["overall"]] = s.get(r["overall"], 0) + 1
        return s

    # ── detail: resolve kind from id, group criteria by name ──────
    @staticmethod
    def target_detail_by_id(pk):
        pk = str(pk)

        ev_qs = CriterionEvidence.objects.filter(intervention_id=pk).select_related("criterion")
        kind = "intervention"
        if not ev_qs.exists():
            ev_qs = CriterionEvidence.objects.filter(national_proposal_id=pk).select_related("criterion")
            kind = "national_proposal"
        if not ev_qs.exists():
            return _err("no evidence for this target", 404)

        model = InterventionProposal if kind == "intervention" else NationalProgramProposal
        t = model.objects.select_related("package", "phase").filter(pk=pk).first()
        if not t:
            return _err("target not found", 404)

        groups, id_to_key = EvidenceCoverageService._grouped_criteria()

        # collapse this target's evidence bands into one row per group
        ev_by_group = {}
        for e in ev_qs:
            gkey = id_to_key.get(e.criterion_id)
            if gkey is None:
                continue
            existing = ev_by_group.get(gkey)
            if existing is None or len(e.data or {}) > len(existing.data or {}):
                ev_by_group[gkey] = e

        per_criterion = []
        counts = {"complete": 0, "incomplete": 0, "empty": 0, "missing": 0}
        for g in groups:
            e = ev_by_group.get(g["key"])
            status, filled, total = EvidenceCoverageService._grade(e, g["header_keys"])
            counts[status] += 1
            per_criterion.append({
                "criterion": g["key"],
                "criterion_id": str(g["ids"][0]), 
                "criterion_name": g["name"],
                "headers": g["headers"],
                "evidence_id": str(e.id) if e else None,
                "data": e.data if e else {},
                "score": e.score if e else None,
                "status": status,
                "filled": filled,
                "total": total,
            })

        total_c = len(groups) or 1
        return _ok({
            "id": str(t.id),
            "kind": kind,
            "reference_number": getattr(t, "reference_number", None),
            "name": getattr(t, "intervention_name", None) or getattr(t, "title", None),
            "package": _rel(getattr(t, "package", None)),
            "phase": _rel(getattr(t, "phase", None)),
            "counts": counts,
            "coverage": {
                "covered": total_c - counts["missing"],
                "total": total_c,
                "percent": round((total_c - counts["missing"]) / total_c * 100),
            },
            "overall": EvidenceCoverageService._overall(counts, total_c),
            "criteria": per_criterion,
        })


# ── helpers ──────────────────────────────────────────────────
def _is_blank(v):
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def _rel(obj):
    if not obj:
        return None
    return {
        "id": str(obj.id),
        "name": getattr(obj, "name", None),
        "batch_number": getattr(obj, "batch_number", None),
    }