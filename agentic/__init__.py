"""
Agentic wrapper  - the seam between BPTAP's app knowledge and AI providers.

Consumers build a Context (knowledge + task contract) and call run().
The wrapper is domain-agnostic: it knows nothing about criteria, scores, or
appraisals — only how to render context, pick a provider, and return a result.

Public API:
    from agentic import Context, run, parse_json
"""
from .context import Context, ContextSource
from .runner import run
from .result import RawResult, parse_json
from .errors import AgenticError, ConfigError, ConnectionErr, ProcessingError

__all__ = [
    "Context", "ContextSource", "run", "RawResult", "parse_json",
    "AgenticError", "ConfigError", "ConnectionErr", "ProcessingError",
]