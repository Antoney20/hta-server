import logging
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from django.db import transaction

from agentic import run as agentic_run
from agentic import AgenticError, ConfigError, ConnectionErr, ProcessingError

from app.models import (
    CriteriaAppraisalTool, PanelAppraisal, AppraisalScore, AppraisalRun,
)
from .context_builder import build_appraisal_context
from .parser import parse_appraisal_response

logger = logging.getLogger(__name__)


def _criterion_map() -> dict[str, CriteriaAppraisalTool]:
    return {c.criteria.strip().lower(): c for c in CriteriaAppraisalTool.objects.all()}


def _persist(target_type, target_id, parsed, result, user, cmap) -> PanelAppraisal:
    """Write one PanelAppraisal + its AppraisalScore rows + the AppraisalRun audit."""
    with transaction.atomic():
        appraisal = PanelAppraisal(success=parsed["success"], created_by=user)
        if target_type == "national_proposal":
            appraisal.national_proposal_id = target_id
        else:
            appraisal.intervention_id = target_id
        appraisal.save()

        total = 0.0
        for row in parsed["scores"]:
            criterion = cmap.get(row["criterion"].strip().lower())
            if criterion is None:
                continue  # model named a criterion we don't have — skip, don't crash
            AppraisalScore.objects.create(
                appraisal=appraisal,
                criterion=criterion,
                ok=row["ok"],
                score=row["score"],
                reasoning=row["reasoning"],
                failure_reason=row["failure_reason"],
            )
            if row["ok"] and row["score"] is not None:
                total += row["score"]

        appraisal.total_score = total
        appraisal.save(update_fields=["total_score"])

        AppraisalRun.objects.create(
            appraisal=appraisal,
            model=None,  # RawResult carries model_name/provider (strings), see note
            prompt_sent=result.rendered,
            raw_response=result.raw,
            parsed_ok=True,
            duration_ms=result.duration_ms,
        )
    return appraisal


def appraise_target(target_type: str, target_id: str, user=None, extra_guidance: str = "") -> dict:
    """
    Full appraisal for ONE target. Never raises — returns a structured result with
    an error_code on failure. Persists on success (and an audit row on failure).
    """
    def _fail(code, message, rendered="", raw=""):
        try:
            AppraisalRun.objects.create(
                prompt_sent=rendered, raw_response=raw,
                parsed_ok=False, error=f"[{code}] {message}",
            )
        except Exception:
            logger.exception("Failed to write failed-run audit record")
        return {"success": False, "target_type": target_type, "target_id": target_id,
                "error": message, "error_code": code, "scores": []}

    # build context
    try:
        context = build_appraisal_context(target_type, target_id, extra_guidance)
    except Exception as e:
        logger.exception("Context build failed for %s %s", target_type, target_id)
        return _fail("processing_error", f"Failed to prepare appraisal input: {e}")

    # run through the wrapper
    try:
        result = agentic_run(context)
    except ConfigError as e:
        return _fail(e.code, e.message)
    except ConnectionErr as e:
        return _fail(e.code, e.message)
    except ProcessingError as e:
        return _fail(e.code, e.message)
    except AgenticError as e:
        return _fail(e.code, e.message)
    except Exception as e:
        logger.exception("Agentic run failed for %s %s", target_type, target_id)
        return _fail("connection_error", f"Unexpected error contacting the model: {e}")

    # parse against the appraisal contract
    try:
        parsed = parse_appraisal_response(result.raw)
    except ProcessingError as e:
        return _fail("processing_error", f"Failed to process the model response: {e}",
                     rendered=result.rendered, raw=result.raw)

    # persist
    try:
        appraisal = _persist(target_type, target_id, parsed, result, user, _criterion_map())
    except Exception as e:
        logger.exception("Persist failed for %s %s", target_type, target_id)
        return _fail("processing_error", f"Scored but failed to save: {e}",
                     rendered=result.rendered, raw=result.raw)

    return {
        "success": parsed["success"],
        "appraisal_id": str(appraisal.id),
        "target_type": target_type,
        "target_id": target_id,
        "total_score": appraisal.total_score,
        "model": result.model_name,
        "provider": result.provider,
        "duration_ms": result.duration_ms,
        "scores": parsed["scores"],
    }


def appraise_targets(targets: list[tuple[str, str]], user=None) -> dict:
    """Parallel appraisal over many targets. Concurrency capped by GEMINI_WORKERS."""
    workers = getattr(settings, "GEMINI_WORKERS", 10)
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(appraise_target, tt, tid, user) for tt, tid in targets]
        for f in futures:
            results.append(f.result())
    return {"results": results, "count": len(results)}


def appraise_repeated(target_type: str, target_id: str, runs: int = 3, user=None) -> dict:
    """
    Run the SAME target N times for accuracy/consistency testing. Each run is a
    separate PanelAppraisal + AppraisalRun, so you can compare score stability
    across runs. Returns every run plus a per-criterion variance summary.
    """
    runs = max(1, min(runs, 20))  # sane cap
    outcomes = []
    with ThreadPoolExecutor(max_workers=getattr(settings, "GEMINI_WORKERS", 10)) as pool:
        futures = [
            pool.submit(appraise_target, target_type, target_id, user)
            for _ in range(runs)
        ]
        for f in futures:
            outcomes.append(f.result())

    return {
        "target_type": target_type,
        "target_id": target_id,
        "runs": len(outcomes),
        "results": outcomes,
        "consistency": _consistency_summary(outcomes),
    }


def _consistency_summary(outcomes: list[dict]) -> list[dict]:
    """
    Per-criterion: how many runs scored it, the distinct scores seen, and the
    spread (min/max). Lets you eyeball whether the model is stable on each criterion.
    """
    per_criterion: dict[str, list[float]] = {}
    for o in outcomes:
        for s in o.get("scores", []):
            if s["ok"] and s["score"] is not None:
                per_criterion.setdefault(s["criterion"], []).append(s["score"])

    summary = []
    for cname, scores in sorted(per_criterion.items()):
        distinct = sorted(set(scores))
        summary.append({
            "criterion": cname,
            "runs_scored": len(scores),
            "distinct_scores": distinct,
            "min": min(scores),
            "max": max(scores),
            "stable": len(distinct) == 1,   # same score every run
        })
    return summary