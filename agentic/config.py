from django.conf import settings
from app.models import AIProviderKey
from types import SimpleNamespace

from .errors import ConfigError


def resolve_model():
    key_row = AIProviderKey.objects.filter(is_active=True, is_default=True).first()
    if key_row is None:
        raise ConfigError("No default active provider key is configured.")

    provider = (key_row.provider or "").strip().lower()
    model_string = (key_row.model_string or "").strip()
    if not model_string:
        raise ConfigError(
            f"The default {provider} key has no model_string set — "
            f"edit it under AI Settings before running appraisals."
        )

    return SimpleNamespace(
        name=key_row.label or provider,
        provider=provider,
        model_string=model_string,
        temperature=key_row.temperature,
        max_tokens=getattr(settings, "AI_MAX_TOKENS", 8192),
    )


def resolve_key(provider: str) -> str:
    row = (
        AIProviderKey.objects
        .filter(provider__iexact=provider, is_active=True, is_default=True)
        .first()
    )
    if row is None:
        raise ConfigError(f"No active API key configured for provider '{provider}'.")
    key = (row.key or "").strip()
    if not key:
        raise ConfigError(f"API key for provider '{provider}' is empty.")
    return key