from agentic import Context
from app.services.criteria_rules import CriteriaRuleService
from app.services.final_template import DecisionTemplateService


OUTPUT_CONTRACT = """\
{
  "scores": [
    {
      "criterion": "<exact criterion name as given>",
      "ok": true,
      "score": <number>,
      "reasoning": "<why this score, citing the specific evidence value and the band applied>",
      "failure_reason": null
    },
    {
      "criterion": "<criterion whose evidence is blank or insufficient>",
      "ok": false,
      "score": null,
      "reasoning": null,
      "failure_reason": "<why it could not be scored, e.g. the evidence for this criterion is blank>"
    }
  ]
}"""

APPRAISAL_INSTRUCTION = """\
Appraise this target against EACH criterion listed in the criteria_evidence source,
and ONLY those criteria. Score every one of them exactly once — no more, no fewer.

Each criterion's evidence is the `values` object inside its criteria_evidence entry.
That object is the ONLY place a score may be drawn from.

For each criterion:
- QUANTITATIVE: take the figure(s) in `values` and apply the criterion's bands from
  criteria_rules to decide the score. Cite the exact value and the band you matched.
- DESCRIPTIVE: read the narrative in `values`, use the criterion's `guides` as
  supporting context, then justify the score against the bands.

The bands in criteria_rules are scoring thresholds ONLY. They are not evidence.
Never lift a value out of a band label to score a criterion.

If a criterion's `values` object is empty, or does not contain the figure or narrative
that criterion needs, set ok=false and give a failure_reason stating the data is blank
or missing (e.g. "morbidity rank is blank in the evidence"). Do NOT guess a number and
do NOT infer one from the bands or from another criterion's evidence."""

APPRAISAL_EXTRA_RULES = """\
- criteria_evidence is the sole source of scoring evidence. Cite the specific value in
  your reasoning for every score.
- Score only the criteria named in criteria_evidence. Do not add, drop, or rename any.
- criteria_rules supplies thresholds and, for descriptive criteria, guides for context —
  never a value to score from.
- A score is valid only with reasoning that cites its evidence value. If you cannot
  justify a score from that criterion's own `values`, return ok=false — never a guess."""


def _load_rules_via_service() -> list[dict]:
    """
    Consume the CriteriaRule SERVICE so appraisal sees the same rules as the app.
    Grouped by criterion name (case-insensitive), carrying each rule's bands.
    """
    envelope = CriteriaRuleService.list_rules({})
    raw = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
    items = raw.get("results", raw) if isinstance(raw, dict) else raw

    by_name: dict[str, dict] = {}
    for r in (items or []):
        cname = (r.get("criterion_name") or r.get("criteria") or "").strip()
        if not cname:
            continue
        key = cname.lower()
        bucket = by_name.setdefault(key, {"criterion": cname, "kind": r.get("kind"), "rules": []})
        for b in (r.get("bands") or []):
            bucket["rules"].append({
                "op": b.get("op"),
                "combo": b.get("combo"),
                "label": b.get("label", ""),
                "score": b.get("score"),
            })

    return list(by_name.values())


def _criteria_evidence(evidence: dict) -> list[dict]:
    """
    Lift each criterion the target actually carries into a compact scoring entry:
    [{criterion, type, values, has_evidence, guides}].

    `values` is the criterion's evidence. If the panel designated specific
    target_fields, narrow to them; otherwise pass the whole evidence dict.
    Entries with empty `values` are KEPT (has_evidence=False) so the model can
    mark them blank rather than silently dropping them.
    """
    criteria = evidence.get("criteria") if isinstance(evidence, dict) else None
    if not isinstance(criteria, list):
        return []

    out = []
    for c in criteria:
        name = c.get("criterion")
        if not name:
            continue

        ev = c.get("evidence") or {}
        target_fields = c.get("target_fields") or []
        values = {f: ev.get(f) for f in target_fields} if target_fields else dict(ev)

        has_evidence = any(v not in (None, "", [], {}) for v in values.values())

        out.append({
            "criterion": name,
            "type": c.get("type"),
            "values": values,
            "has_evidence": has_evidence,
            "guides": c.get("guides") or [],
        })
    return out


def build_appraisal_context(target_type: str, target_id: str, extra_guidance: str = "") -> Context:
    """
    Assemble the appraisal Context for ONE target.

    Sends the target's own criteria_evidence plus the bands for exactly those
    criteria — not every rule in the app — so the model scores the template it was
    given and nothing else.
    """
    evidence = DecisionTemplateService.evidence_for_target(target_type, target_id)
    criteria_evidence = _criteria_evidence(evidence)

    # Constrain the rules to the criteria this target carries. Fall back to the full
    # set only if we could not resolve any names, so we never send an empty ruleset.
    names = {ce["criterion"].strip().lower() for ce in criteria_evidence if ce.get("criterion")}
    rules = _load_rules_via_service()
    if names:
        rules = [r for r in rules if (r.get("criterion") or "").strip().lower() in names] or rules

    ctx = Context(
        task="appraisal",
        instruction=APPRAISAL_INSTRUCTION,
        output_contract=OUTPUT_CONTRACT,
        extra_system=APPRAISAL_EXTRA_RULES,
    )

    ctx.add("criteria_rules", rules)
    ctx.add("criteria_evidence", criteria_evidence)

    if extra_guidance.strip():
        ctx.add("panel_guidance", extra_guidance.strip())

    return ctx