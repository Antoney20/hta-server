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
      "reasoning": "<why this score: cite the specific evidence value, the band applied, and — if a reference_guide informed the reading — what it says>",
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
YOUR INPUTS — read these definitions first. Each is supplied to you as a labelled
source. Know what each one is and is not before you score anything.

- target: which item you are appraising and the package it belongs to. Context only;
  it carries no evidence and no scores.

- criteria_evidence: the list of criteria to score, and for EACH one a `values` object
  holding that criterion's evidence (the figures or narrative gathered for this target).
  This is the ONLY source of scoring evidence. A criterion's `values` is the ONLY place
  its score may be drawn from. Some entries also carry `guides` (brief supporting notes)
  and a `type` of "quantitative" or "descriptive".

- criteria_rules: for each criterion, its scoring `bands` — the thresholds that map an
  evidence value to a score. Bands are the scoring scale ONLY. They are NOT evidence:
  never read a value out of a band label. A criterion in this source may also carry
  `reference_guides` (defined next).

- reference_guides (optional, inside criteria_rules): extra supporting references for a
  criterion — for example a grade table explaining what a severity level means. Each has
  a `scope`: "criterion" (general, always applies) or "package" (applies only if it fits
  this target's package). They help you INTERPRET evidence and JUSTIFY a score; they are
  NOT evidence and NOT bands. A criterion may have none — that is normal.

- panel_guidance (optional): extra instructions from the human panel for this run. Honour
  it, but it never overrides the rule that a score must come from the criterion's values.

In short: score FROM criteria_evidence.values, ON the scale of criteria_rules.bands,
INTERPRETED with reference_guides — and never mix those roles up.

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

Some criteria may also carry `reference_guides` in criteria_rules. When present, use
them; when absent, that is normal — do not expect them. Apply "criterion"-scope guides
always and "package"-scope guides only when they fit this target's package. They help
you interpret the evidence and explain WHY this evidence earns this score — never read a
score or figure out of one, never let one override a band, and never treat a criterion
as scorable just because a guide exists. The score always comes from the criterion's own
`values`.

If a criterion's `values` object is empty, or does not contain the figure or narrative
that criterion needs, set ok=false and give a failure_reason stating the data is blank
or missing (e.g. "morbidity rank is blank in the evidence"). A reference guide does not
change this — a rich guide never makes a blank criterion scorable. Do NOT guess a number
and do NOT infer one from the bands, from a reference guide, or from another criterion's
evidence.


REFERENCE GUIDES (optional):
A criterion in criteria_rules may include `reference_guides`. When it does, use them.
When a criterion has none, it simply has none — do not expect them and do not treat
their absence as a problem. Each guide has a `scope`:
- "criterion": a general reference for this criterion, not tied to any package. Always
  apply it.
- "package": written for a specific package. Apply it only when it fits this target's
  package; if it names a different package, ignore it.
Reference guides do two jobs, both supporting only:
1. They help you INTERPRET the evidence — e.g. a grade table that says what a given
   severity level means — so you read the `values` correctly before matching a band.
2. They help you JUSTIFY the score — explain in your reasoning WHY this evidence earns
   this number (for example, why a Grade 4 event lands where it does on the scale).
They are NOT evidence and NOT bands. Never read a score or a figure out of a reference
guide, never let one override a band, and never treat a criterion as scorable just
because a guide exists. The score always comes from the criterion's own `values`.

If a criterion's `values` object is empty, or does not contain the figure or narrative
that criterion needs, set ok=false and give a failure_reason stating the data is blank
or missing (e.g. "morbidity rank is blank in the evidence"). A reference guide does not
change this — a rich guide never makes a blank criterion scorable. Do NOT guess a number
and do NOT infer one from the bands, from a reference guide, or from another criterion's
evidence."""

APPRAISAL_EXTRA_RULES = """\
- criteria_evidence is the sole source of scoring evidence. Cite the specific value in
  your reasoning for every score.
- Score only the criteria named in criteria_evidence. Do not add, drop, or rename any.
- criteria_rules supplies thresholds and, for descriptive criteria, guides for context —
  never a value to score from.
- reference_guides, when present, are optional supporting references. Use "criterion"-
  scope guides always and "package"-scope guides only when they match this target's
  package. They help you interpret the evidence and explain why a score was given —
  never as the source of the value being scored, and never as grounds to score a
  criterion whose own values are blank.
- A score is valid only with reasoning that cites its evidence value. If you cannot
  justify a score from that criterion's own `values`, return ok=false — never a guess."""

# def _load_rules_via_service() -> list[dict]:
#     """
#     Consume the CriteriaRule SERVICE so appraisal sees the same rules as the app.
#     Grouped by criterion name (case-insensitive), carrying each rule's bands.
#     """
#     envelope = CriteriaRuleService.list_rules({})
#     raw = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
#     items = raw.get("results", raw) if isinstance(raw, dict) else raw

#     by_name: dict[str, dict] = {}
#     for r in (items or []):
#         cname = (r.get("criterion_name") or r.get("criteria") or "").strip()
#         if not cname:
#             continue
#         key = cname.lower()
#         bucket = by_name.setdefault(key, {"criterion": cname, "kind": r.get("kind"), "rules": []})
#         for b in (r.get("bands") or []):
#             bucket["rules"].append({
#                 "op": b.get("op"),
#                 "combo": b.get("combo"),
#                 "label": b.get("label", ""),
#                 "score": b.get("score"),
#             })

#     return list(by_name.values())


def _load_rules_via_service() -> list[dict]:
    envelope = CriteriaRuleService.list_rules({})
    raw = envelope.get("data", envelope) if isinstance(envelope, dict) else envelope
    items = raw.get("results", raw) if isinstance(raw, dict) else raw

    by_name: dict[str, dict] = {}
    for r in (items or []):
        cname = (r.get("criterion_name") or r.get("criteria") or "").strip()
        if not cname:
            continue
        key = cname.lower()
        bucket = by_name.setdefault(key, {
            "criterion": cname, "kind": r.get("kind"), "rules": [], "_scales": [],
        })
        for b in (r.get("bands") or []):
            bucket["rules"].append({
                "op": b.get("op"),
                "combo": b.get("combo"),
                "label": b.get("label", ""),
                "score": b.get("score"),
            })
        bucket["_scales"].extend(r.get("scales") or [])   # filtered by package later

    return list(by_name.values())

def _reference_guides(scales: list[dict], package: str) -> list[dict]:
    """
    Reference guides are applicable to this target's package.
    Each guide `label` names the package it was written for (e.g. "Renal package").
    If the target's package matches, keep only those; otherwise keep all — every guide
    stays tagged with its package so the model can pick the relevant one and never
    treats another package's guide as authoritative. Reference material, never be evidence.
    """
    tagged = [{
        "package": s.get("label", ""),
        "source":  s.get("source", ""),
        "notes":   s.get("description", ""),
        "data":    s.get("data"),
    } for s in (scales or []) if s.get("active", True)]

    pkg = (package or "").strip().lower()
    if not pkg:
        return tagged
    matched = [
        g for g in tagged
        if pkg in (g["package"] or "").lower() or pkg in (g["source"] or "").lower()
    ]
    return matched or tagged

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


# def build_appraisal_context(target_type: str, target_id: str, extra_guidance: str = "") -> Context:
#     """
#     Assemble the appraisal Context for ONE target.

#     Sends the target's own criteria_evidence plus the bands for exactly those
#     criteria — not every rule in the app — so the model scores the template it was
#     given and nothing else.
#     """
#     evidence = DecisionTemplateService.evidence_for_target(target_type, target_id)
#     criteria_evidence = _criteria_evidence(evidence)

#     # Constrain the rules to the criteria this target carries. Fall back to the full
#     # set only if we could not resolve any names, so we never send an empty ruleset.
#     names = {ce["criterion"].strip().lower() for ce in criteria_evidence if ce.get("criterion")}
#     rules = _load_rules_via_service()
#     if names:
#         rules = [r for r in rules if (r.get("criterion") or "").strip().lower() in names] or rules

#     ctx = Context(
#         task="appraisal",
#         instruction=APPRAISAL_INSTRUCTION,
#         output_contract=OUTPUT_CONTRACT,
#         extra_system=APPRAISAL_EXTRA_RULES,
#     )

#     ctx.add("criteria_rules", rules)
#     ctx.add("criteria_evidence", criteria_evidence)

#     if extra_guidance.strip():
#         ctx.add("panel_guidance", extra_guidance.strip())

#     return ctx


def build_appraisal_context(target_type: str, target_id: str, extra_guidance: str = "") -> Context:
    evidence = DecisionTemplateService.evidence_for_target(target_type, target_id)
    package = (evidence.get("package") if isinstance(evidence, dict) else None) or ""
    criteria_evidence = _criteria_evidence(evidence)

    names = {ce["criterion"].strip().lower() for ce in criteria_evidence if ce.get("criterion")}
    rules = _load_rules_via_service()
    if names:
        rules = [r for r in rules if (r.get("criterion") or "").strip().lower() in names] or rules

    # package-relevant reference guides, per criterion
    for r in rules:
        r["reference_guides"] = _reference_guides(r.pop("_scales", []), package)

    ctx = Context(
        task="appraisal",
        instruction=APPRAISAL_INSTRUCTION,
        output_contract=OUTPUT_CONTRACT,
        extra_system=APPRAISAL_EXTRA_RULES,
    )

    ctx.add("target", {"type": target_type, "package": package or "unspecified"})
    ctx.add("criteria_rules", rules)
    ctx.add("criteria_evidence", criteria_evidence)

    if extra_guidance.strip():
        ctx.add("panel_guidance", extra_guidance.strip())

    return ctx