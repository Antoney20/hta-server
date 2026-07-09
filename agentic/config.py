from app.models import AIModel, AIProviderKey

from .errors import ConfigError




def resolve_model() -> AIModel:
    model = AIModel.objects.filter(is_default=True, is_active=True).first()
    if model is None:
        raise ConfigError("No default active AI model is configured.")
    return model


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