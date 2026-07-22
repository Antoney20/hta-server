from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from app.models import AppraisalScore, PanelAppraisal
from app.services.appraisal_panel import _get_or_404




def _label(v):
    if v is None:
        return None
    return getattr(v, "name", None) or getattr(v, "title", None) or str(v)


def _target_meta(t):
    if t is None:
        return {"name": "—", "reference_number": None, "package": None, "phase": None}
    return {
        "name": getattr(t, "intervention_name", None) or getattr(t, "title", None) or "—",
        "reference_number": getattr(t, "reference_number", None),
        "package": _label(getattr(t, "package", None)),   
        "phase":   _label(getattr(t, "phase", None)),
    }


def _score_block(s):
    return {
        "id": str(s.id),
        "criterion_id": str(s.criterion_id),
        "criterion": s.criterion.criteria,
        "ok": s.ok,
        "score": s.score,                   
        "final_score": s.final_score,        
        "effective_score": s.effective_score,
        "verified": s.verified,
        "edited": s.edited,
        "reasoning": s.reasoning,         
        "notes": s.notes,                  
        "failure_reason": s.failure_reason,
    }


def _appraisal_block(ap):
    return {
        "id": str(ap.id),
        "success": ap.success,
        "rank": ap.rank,
        "selected": ap.selected,
        "final_comments": ap.final_comments,
        "created_at": ap.created_at.isoformat(),
        "created_by": getattr(ap.created_by, "username", None),
        "scores": [_score_block(s) for s in ap.scores.all()],
    }


def get_agentic_results(target=None):
    """
    Per-target results, grouped so repeated runs on one target collapse into a
    single row with a run count (drift watchdog). Newest-first within each group.
    """
    qs = (
        PanelAppraisal.objects
        .select_related("intervention", "national_proposal", "created_by")
        .prefetch_related("scores__criterion")
        .order_by("-created_at")
    )
    if target:
        qs = qs.filter(Q(intervention_id=target) | Q(national_proposal_id=target))

    groups: dict[tuple, dict] = {}
    for ap in qs:
        tid = str(ap.intervention_id or ap.national_proposal_id)
        key = (ap.target_type, tid)

        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "target_type": ap.target_type,
                "target_id": tid,
                **_target_meta(ap.target),
                "appraisal_count": 0,               # repeated runs
                "latest_appraisal_id": str(ap.id),  # qs newest-first
                "appraisals": [],
            }
        g["appraisal_count"] += 1
        g["appraisals"].append(_appraisal_block(ap))

    return list(groups.values())

def edit_score(score_id, *, final_score=None, verified=None, notes=None):
    try:
        s = AppraisalScore.objects.select_related("criterion").get(pk=score_id)
    except AppraisalScore.DoesNotExist:
        return None
    if final_score is not None:
        s.final_score = final_score
        s.edited = True
    if verified is not None:
        s.verified = verified
    if notes is not None:
        s.notes = notes
    s.save()
    return _score_block(s)




def delete_appraisal(appraisal_id):
    """Delete a whole run (cascades its scores). Returns deleted id or None."""
    try:
        ap = PanelAppraisal.objects.get(pk=appraisal_id)
    except PanelAppraisal.DoesNotExist:
        return None
    ap.delete()
    return str(appraisal_id)


def delete_score(score_id):
    """Delete a single criterion score."""
    try:
        s = AppraisalScore.objects.get(pk=score_id)
    except AppraisalScore.DoesNotExist:
        return None
    s.delete()
    return str(score_id)


def bulk_delete_appraisals(ids):
    """Delete many runs at once. Returns {requested, deleted, missing}."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return {"requested": 0, "deleted": 0, "missing": []}
    qs = PanelAppraisal.objects.filter(pk__in=ids)
    found = set(str(pk) for pk in qs.values_list("pk", flat=True))
    deleted, _ = qs.delete()
    return {
        "requested": len(ids),
        "deleted": len(found),       
        "missing": [i for i in ids if str(i) not in found],
    }


def bulk_delete_scores(ids):
    """Delete many individual scores at once."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        return {"requested": 0, "deleted": 0, "missing": []}
    qs = AppraisalScore.objects.filter(pk__in=ids)
    found = set(str(pk) for pk in qs.values_list("pk", flat=True))
    qs.delete()
    return {
        "requested": len(ids),
        "deleted": len(found),
        "missing": [i for i in ids if str(i) not in found],
    }
    


@transaction.atomic
def select_appraisal(appraisal_id, *, selected=True):
    appr = _get_or_404(PanelAppraisal, appraisal_id)
    if appr is None:
        return None
    if selected:                              # one per target — clear siblings
        sibs = PanelAppraisal.objects.filter(selected=True)
        sibs = (sibs.filter(intervention_id=appr.intervention_id) if appr.intervention_id
                else sibs.filter(national_proposal_id=appr.national_proposal_id))
        sibs.exclude(pk=appr.pk).update(selected=False)
    appr.selected = bool(selected)
    appr.save(update_fields=["selected", "updated_at"])
    return {"id": str(appr.pk), "selected": appr.selected}


def set_comment(appraisal_id, *, comments):   # panel: add / edit
    appr = _get_or_404(PanelAppraisal, appraisal_id)
    if appr is None:
        return None
    appr.final_comments = comments
    appr.save(update_fields=["final_comments", "updated_at"])
    return {"id": str(appr.pk), "final_comments": appr.final_comments}


def clear_comment(appraisal_id):              # admin: delete
    appr = _get_or_404(PanelAppraisal, appraisal_id)
    if appr is None:
        return None
    appr.final_comments = None
    appr.save(update_fields=["final_comments", "updated_at"])
    return {"id": str(appr.pk), "final_comments": None}

@transaction.atomic
def bulk_set_selected(appraisal_ids, *, selected=True):
    ids = [i for i in (appraisal_ids or []) if i]
    if selected:                              
        done = [out["id"] for aid in ids
                if (out := select_appraisal(aid, selected=True))]
        return {"count": len(done), "selected": True, "ids": done}
    updated = (                            
        PanelAppraisal.objects
        .filter(pk__in=ids)
        .update(selected=False, updated_at=timezone.now())
    )
    return {"count": updated, "selected": False, "ids": []}