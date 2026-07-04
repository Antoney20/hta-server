"""One extractor per criterion. Same contract for all; only the scope differs.

Each agent sees ONLY its own criterion's raw data plus the shared guides. Narrow
scope is the main reproducibility lever — there is almost nowhere for the model to
wander. The agent extracts; it never scores.
"""

import json

from .client import call_gemini
from .protocol import CRITERIA, DROP_REASONS

# output schema. confidence + uncertain are required so the "if unsure, flag it" rule
# always gets answered. value/unit are optional (left out when there's no number).
AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string", "enum": list(CRITERIA)},
                    "kept": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "raw": {"type": "string"},   
                                "value": {"type": "number"},  
                                "unit": {"type": "string"},
                                "confidence": {"type": "string", "enum": ["high", "moderate", "low"]},
                                "uncertain": {"type": "boolean"},
                                "why": {"type": "string"},     
                            },
                            "required": ["field", "raw", "confidence", "uncertain", "why"],
                        },
                    },
                    "dropped": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "reason": {"type": "string", "enum": list(DROP_REASONS)},
                                "why": {"type": "string"},      # plain explanation
                            },
                            "required": ["field", "reason", "why"],
                        },
                    },
                },
                "required": ["criterion", "kept", "dropped"],
            },
        },
    },
    "required": ["results"],
}

SYSTEM = (
    "You extract evidence for ONE intervention across ALL of the listed criteria in a "
    "single pass. Use the guides (ICD-11 code, disease definition, intervention name, "
    "routing decision, justification) to understand the intervention and resolve "
    "ambiguous values consistently. Return one `results` entry per criterion. "
    "Rules you MUST follow: "
    "(1) Extract figures into `raw`; never paraphrase a number into prose. "
    "Give `value` and `unit` when a clean number exists. "
    "(2) For each criterion, keep ONLY the fields listed as important for it; log every "
    "other field in `dropped` with a `reason` from the allowed list. "
    "(3) For EVERY kept and dropped item write a `why`: a clear explanation of the "
    "decision. Be factual; a phrase or a couple of sentences as the case needs. "
    "(4) Prefer the listed primary endpoints; demote non-primary duplicates with reason "
    "'superseded'. "
    "(5) If a value is ambiguous or you are not fully certain, set uncertain=true and "
    "confidence='low' — do NOT guess. "
    "(6) Never invent a value that is not in the input."
)


def run_agent(data, guides):
    """One call for the whole intervention. Returns the list of per-criterion results,
    each with its kept/dropped items."""
    user = json.dumps(
        {
            "criteria": {
                crit: {
                    "important_fields": CRITERIA[crit]["metrics"],
                    "primary_fields": CRITERIA[crit]["primary"],
                    "raw_data": (data or {}).get(crit) or {},
                }
                for crit in CRITERIA
            },
            "allowed_drop_reasons": DROP_REASONS,
            "guides": guides,
        },
        ensure_ascii=False,
        sort_keys=True, 
    )
    out = call_gemini(SYSTEM, user, AGENT_SCHEMA)
    return out.get("results", [])