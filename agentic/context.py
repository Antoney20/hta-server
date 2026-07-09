from dataclasses import dataclass, field
from typing import Any
BASE_SYSTEM_CONTEXT = """\
You are an evidence-appraisal assistant for Kenya's Health Technology Assessment \
(HTA) process, operating under the Social Health Insurance Act. You support the \
Benefits Package Technical Advisory Panel (BPTAP) in assessing health interventions \
and national programs for inclusion in Kenya's national benefits package.

Operating principles you must follow at all times:
- Respond only in clear, professional English.
- Ground every judgement in the evidence and rules provided to you. Never invent \
facts, figures, studies, or citations. If the evidence does not support a \
conclusion, say so explicitly rather than guessing.
- Frame reasoning in the Kenyan context: the SHA Fund, county-level equity, \
resource constraints, and national health priorities where relevant.
- Where established instruments are referenced in your inputs, apply them faithfully and name them in your reasoning.
- You perform descriptive and analytical work. You do not make final funding \
decisions — the panel does. Your role is to structure evidence and justify \
assessments so a human panel can decide accountably.
- Every conclusion you output MUST be accompanied by explicit reasoning that \
cites the specific evidence or rule it rests on.
- Return your answer strictly in the requested structured format. Output the \
structure and nothing else — no preamble, no commentary, no markdown fences.
"""


@dataclass
class ContextSource:
    """One labelled piece of app knowledge the agent reasons over."""
    label: str          # "evidence", "criteria_rules",  ...
    content: Any        # dict / list / str — serialized at render time


@dataclass
class Context:
    """
    Provider-agnostic bundle handed to the wrapper.

      instruction     — what to do, in plain terms (layered atop BASE_SYSTEM_CONTEXT)
      sources         — the knowledge the agent reasons over
      output_contract — description of the exact structured shape required back
      task            — tag for logging / audit / per-task template lookup
      extra_system    — optional extra standing rules for this task (appended to base)

    Consumers build this. The wrapper renders and runs it, knowing nothing of the domain.
    """
    instruction: str
    sources: list[ContextSource] = field(default_factory=list)
    output_contract: str = ""
    task: str = "generic"
    extra_system: str = ""

    def add(self, label: str, content: Any) -> "Context":
        """Fluent: ctx.add('evidence', payload).add('rules', rules)"""
        self.sources.append(ContextSource(label=label, content=content))
        return self

    def system_context(self) -> str:
        """Base framing plus any task-specific standing rules."""
        if self.extra_system.strip():
            return f"{BASE_SYSTEM_CONTEXT}\n\nAdditional rules for this task:\n{self.extra_system.strip()}"
        return BASE_SYSTEM_CONTEXT