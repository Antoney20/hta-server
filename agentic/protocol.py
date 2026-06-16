"""The extraction protocol — the spine of the agentic layer.

Importance is DEFINED HERE, not judged freely by the model. Each agent maps the
raw EvidenceExtraction.data onto the metric defines in the agentic protocol below; anything outside a slot
is dropped with a reason from the fixed vocabulary. Bump PROTOCOL_VERSION whenever
any rule below changes — it is stored on every result
"""

PROTOCOL_VERSION = "v1.0"

DROP_REASONS = {
    "not_in_protocol": "Not a scoreable metric for this criterion.",
    "no_usable_value": "Present but no parseable value.",
    "superseded": "A primary endpoint was preferred over this secondary one.",
    "duplicate": "Same metric reported more than once.",
    "low_confidence": "Extracted but flagged uncertain for panel review.",
}

# The 'guides' — shared in all context
# value is always resolved the same way. These are not extracted; they are already
# clean (routing fields are real columns; name/justification come from the proposal).
GUIDE_FIELDS = [
    "routing_decision",
    "icd_11",
    "disease_definition",
    "intervention_name",
    "justification",
]

# For every criteria important metrics. 'metrics' = the only fields worth keeping;
# 'primary' = preferred endpoints when several are present (others -> 'superseded').
# We can't pick all the metrics from the form - the main aim is to get the most importnat metric
CRITERIA = {
    "clinical_effectiveness": {
        "metrics": [
            "survival_rate", "hazard_ratio", "response_rate", "remission_rate",
            "hospitalisation_rate", "progression_free_rate", "response_ratio",
        ],
        "primary": ["survival_rate", "hazard_ratio"],
    },
    "safety": {
        "metrics": [
            "odds_ratio", "relative_risk", "risk_difference",
            "total_adverse_events", "serious_adverse_events", "drug_toxicity",
        ],
        "primary": ["serious_adverse_events", "relative_risk"],
    },
    "quality": {
        "metrics": [
            "treatment_adherence_rate", "treatment_completion_rate", "patient_satisfaction",
        ],
        "primary": ["treatment_adherence_rate"],
    },
    "burden_of_disease": {
        "metrics": [
            "dalys", "qalys", "case_fatality_rate", "morbidity_rate",
            "mortality_rate", "yll", "yld",
        ],
        "primary": ["dalys", "mortality_rate"],
    },
}