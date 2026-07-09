from agentic import Context
from app.models import CriteriaAppraisalTool, CriteriaRule, CriteriaGuideDocument
from app.services.final_template import DecisionTemplateService


OUTPUT_CONTRACT = """\
{
  "scores": [
    {
      "criterion": "<exact criterion name as given>",
      "ok": true,
      "score": <number>,
      "reasoning": "<why this score, citing the specific evidence or rule used>",
      "failure_reason": null
    },
    {
      "criterion": "<criterion with no usable evidence>",
      "ok": false,
      "score": null,
      "reasoning": null,
      "failure_reason": "<why it could not be scored, e.g. no data in the evidence>"
    }
  ]
}"""

APPRAISAL_INSTRUCTION = """\
Appraise this target against EACH criterion listed in the criteria_rules source.
For each criterion:
- If the evidence supports a score, set ok=true, assign the score per the criterion's
  scoring bands/rules, and give reasoning that cites the specific evidence value or
  rule you applied.
- If the evidence does not contain what the criterion needs, set ok=false and give a
  clear failure_reason (e.g. "no cost-effectiveness data provided").
Score every criterion exactly once. Do not invent evidence. Do not omit any criterion."""

APPRAISAL_EXTRA_RULES = """\
- Use only the criteria named in the criteria_rules source — do not add or rename any.
- A score is only valid with reasoning that cites its evidence. If you cannot justify
  a score from the evidence, mark it ok=false rather than guessing a number."""


def _load_criteria_and_rules() -> list[dict]:
    """Criteria with their bands/rules, grouped by criteria name (case-insensitive)."""
    rules_by_name: dict[str, list[dict]] = {}
    for r in CriteriaRule.objects.select_related("criterion").all():
        cname = r.criterion.criteria.strip().lower()
        rules_by_name.setdefault(cname, []).append({
            "band": getattr(r, "band", None),
            "label": getattr(r, "label", ""),
            "condition": getattr(r, "condition", ""),
        })

    out = []
    for c in CriteriaAppraisalTool.objects.all().order_by("criteria"):
        out.append({
            "criterion": c.criteria,
            "description": getattr(c, "description", ""),
            "rules": rules_by_name.get(c.criteria.strip().lower(), []),
        })
    return out


def _load_guides() -> list[dict]:
    return [
        {
            "criterion": g.criterion.criteria if getattr(g, "criterion_id", None) else None,
            "text": g.text,
        }
        for g in CriteriaGuideDocument.objects.select_related("criterion").all()
    ]


def build_appraisal_context(target_type: str, target_id: str, extra_guidance: str = "") -> Context:
    """
    Assemble the appraisal Context: instruction + Kenya-HTA rules + the three sources
    (criteria_rules, evidence, guides). `extra_guidance` lets a panel note steer a run.
    """
    ctx = Context(
        task="appraisal",
        instruction=APPRAISAL_INSTRUCTION,
        output_contract=OUTPUT_CONTRACT,
        extra_system=APPRAISAL_EXTRA_RULES,
    )
    ctx.add("criteria_rules", _load_criteria_and_rules())
    ctx.add("evidence", DecisionTemplateService.payload_for(target_type, target_id))
    ctx.add("guides", _load_guides())
    if extra_guidance.strip():
        ctx.add("panel_guidance", extra_guidance.strip())
    return ctx