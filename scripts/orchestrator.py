"""
The orchestrator. (your 'Prefect thing'). Its job is to NOT trust the agents.

It runs one call per intervention, throws away anything malformed, fills in any
criterion the model skipped, and merges everything into one clean result. Corrupt
output never becomes a value; uncertain output becomes a flag, not a guess.
"""

from .agents import run_agent
from .protocol import CRITERIA, GUIDE_FIELDS, PROTOCOL_VERSION


def build_guides(extraction):
    """Shared context for the agent: ICD-11 code, disease definition, routing decision,
    intervention name and justification. Helps it read the numbers the same way each run."""
    p = getattr(extraction, "proposal", None)
    raw = {
        "routing_decision": getattr(extraction, "routing_decision", "") or "",
        "icd_11": getattr(extraction, "icd_11", "") or "",
        "disease_definition": getattr(extraction, "disease_definition", "") or "",
        "intervention_name": getattr(p, "name", None) or getattr(p, "title", "") or "",
        "justification": getattr(p, "justification", "") or "",
    }
    return {k: raw.get(k, "") for k in GUIDE_FIELDS}


def _clean_one(result):
    """Keep only well-formed kept/dropped items for a single criterion. Extra keys
    (raw, value, unit, why, ...) ride along untouched."""
    kept = [
        k for k in result.get("kept", [])
        if isinstance(k, dict) and k.get("field") and k.get("confidence")
    ]
    dropped = [
        d for d in result.get("dropped", [])
        if isinstance(d, dict) and d.get("field") and d.get("reason")
    ]
    return {"kept": kept, "dropped": dropped}


def build_reasoning(merged, dropped, flags):
    """Plain per-criterion narration (kept / dropped / flagged / failed). None-safe.
    Swap in an LLM later if you want nicer prose — feed it these same inputs so it can
    only rephrase, never change the story."""
    lines = {}
    for crit in sorted(merged):
        kept_fields = sorted(k["field"] for k in merged[crit] if k.get("field"))
        crit_drops = sorted(
            (d for d in dropped if d.get("criterion") == crit),
            key=lambda d: d.get("field") or "",
        )
        crit_flag_fields = sorted(
            f["field"] for f in flags
            if f.get("criterion") == crit and f.get("flag") == "uncertain" and f.get("field")
        )
        agent_failed = any(
            f.get("criterion") == crit and f.get("flag") == "agent_failed" for f in flags
        )

        parts = []
        if agent_failed:
            parts.append("Extraction failed for this criterion — no data captured.")
        elif kept_fields:
            parts.append("Kept: " + ", ".join(kept_fields) + ".")
        else:
            parts.append("No scoreable metric extracted.")
        if crit_drops:
            parts.append("Dropped: " + "; ".join(
                f"{d['field']} ({d['reason']})" for d in crit_drops) + ".")
        if crit_flag_fields:
            parts.append("Flagged uncertain: " + ", ".join(crit_flag_fields)
                         + " — review before scoring.")
        lines[crit] = " ".join(parts)
    return lines


def merge_results(results, call_error=None):
    """Merge the agent's per-criterion output into one result. We walk the canonical
    criteria list, so a criterion the model skipped still shows up (as a failure).
    Status:
        'ok'      — every criterion came back
        'partial' — some criteria missing but something was still extracted
        'failed'  — nothing came back at all
    """
    by_crit = {}
    for r in results or []:
        crit = r.get("criterion")
        if crit in CRITERIA:
            by_crit[crit] = _clean_one(r)

    merged, dropped, flags, errors = {}, [], [], []
    for crit in sorted(CRITERIA):
        r = by_crit.get(crit)
        if r is None:
            err = call_error or "no result returned for this criterion"
            flags.append({"criterion": crit, "field": None, "flag": "agent_failed", "error": err})
            errors.append({"criterion": crit, "error": err})
            merged[crit] = []
            continue
        merged[crit] = r["kept"]
        for d in r["dropped"]:
            dropped.append({"criterion": crit, **d})
        for k in r["kept"]:
            if k.get("uncertain"):
                flags.append({"criterion": crit, "field": k["field"], "flag": "uncertain"})

    any_kept = any(merged[c] for c in merged)
    status = "ok" if not errors else ("partial" if any_kept else "failed")
    return {
        "data": merged,                 # clean values (the AI output)
        "dropped": dropped,             # [{criterion, field, reason, why}]
        "flags": flags,                 # uncertainty / failure flags
        "reasoning": build_reasoning(merged, dropped, flags),
        "status": status,
        "errors": errors,
    }


def run_intervention(data, guides, retries=1):
    """One intervention end to end: call the agent (with a single retry), then merge.
    Never raises — a total failure comes back as status 'failed' with the cause."""
    last = None
    for _ in range(retries + 1):
        try:
            return merge_results(run_agent(data or {}, guides))
        except Exception as exc:  # whole call blew up — try once more, then report
            last = exc
    return merge_results([], call_error=str(last))


def run_workflow(extraction):
    """Single-record path."""
    guides = build_guides(extraction)
    result = run_intervention(extraction.data or {}, guides)
    result["protocol_version"] = PROTOCOL_VERSION
    return result