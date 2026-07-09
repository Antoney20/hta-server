import time
import logging
from .context import Context
from .render import render
from .config import resolve_model, resolve_key
from .providers import get_provider
from .result import RawResult
from .errors import AgenticError, ConfigError, ConnectionErr, ProcessingError

logger = logging.getLogger(__name__)


def run(context: Context) -> RawResult:
    """
    Execute one agentic call for the given Context.

    Raises (typed) on failure so the consumer can branch on error code:
      ConfigError      — model/key/config problem
      ConnectionErr    — provider unreachable / auth / rate limit
      ProcessingError  — provider returned nothing usable

    Returns RawResult on success — the consumer parses .raw and maps to its models.
    """
    model = resolve_model()
    api_key = resolve_key(model.provider)

    provider = get_provider(
        provider=model.provider,
        api_key=api_key,
        model_string=model.model_string,
        temperature=model.temperature,
        max_tokens=model.max_tokens,
    )

    rendered = render(context)

    started = time.monotonic()
    raw = provider.run(rendered)
    duration_ms = int((time.monotonic() - started) * 1000)

    if not (raw or "").strip():
        raise ProcessingError("Provider returned an empty response.")

    return RawResult(
        raw=raw,
        rendered=rendered,
        task=context.task,
        model_name=model.name,
        provider=model.provider,
        duration_ms=duration_ms,
    )