import json
import re
from dataclasses import dataclass
from typing import Any, Optional
from .errors import ProcessingError


@dataclass
class RawResult:
    """
    What the wrapper returns. Carries the raw output plus the rendered input and
    model info so any downstream decision is auditable. Consumers parse `raw`
    (optionally via parse_json) and map it to their own models.
    """
    raw: str
    rendered: str
    task: str
    model_name: str
    provider: str
    duration_ms: Optional[int] = None


def _strip_fences(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def parse_json(raw: str) -> Any:
    """
    Generic: strip fences, parse JSON, return the object. Raises ProcessingError
    on failure. This is plumbing only — it does NOT enforce any domain shape.
    Consumers validate the parsed structure against their own contract.
    """
    try:
        return json.loads(_strip_fences(raw))
    except json.JSONDecodeError as e:
        raise ProcessingError(f"Model output was not valid JSON: {e}")