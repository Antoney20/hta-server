from agentic import parse_json


def parse_appraisal_response(raw: str) -> dict:
    """
    Validate the model's output against the appraisal contract, per criterion:
      ok=True  → needs a numeric score AND non-empty reasoning (else demoted to failure)
      ok=False → needs a non-empty failure_reason (else synthesised)

    Returns {"success": bool, "scores": [ {criterion, ok, score, reasoning, failure_reason} ]}.
    Raises ProcessingError (from parse_json) only if the whole payload is unparseable.
    """
    data = parse_json(raw)  # generic strip-fences + json.loads; raises ProcessingError

    rows = data.get("scores") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        from agentic import ProcessingError
        raise ProcessingError("Response missing a 'scores' list.")

    cleaned = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        criterion = (item.get("criterion") or "").strip()
        if not criterion:
            continue

        ok = bool(item.get("ok"))
        score = item.get("score")
        reasoning = (item.get("reasoning") or "").strip()
        failure = (item.get("failure_reason") or "").strip()

        if ok:
            # A scored criterion MUST have a number and reasoning — the ethical wall.
            if not isinstance(score, (int, float)) or not reasoning:
                cleaned.append({
                    "criterion": criterion, "ok": False, "score": None,
                    "reasoning": None,
                    "failure_reason": "Model returned a score without valid reasoning or value.",
                })
                continue
            cleaned.append({
                "criterion": criterion, "ok": True, "score": float(score),
                "reasoning": reasoning, "failure_reason": None,
            })
        else:
            cleaned.append({
                "criterion": criterion, "ok": False, "score": None, "reasoning": None,
                "failure_reason": failure or "No data available to score this criterion.",
            })

    success = bool(cleaned) and all(r["ok"] for r in cleaned)
    return {"success": success, "scores": cleaned}