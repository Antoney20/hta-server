from .base import Provider
from .openrouter import OpenRouterProvider
from .gemini import GeminiProvider
from ..errors import ConfigError

_REGISTRY = {
    "openrouter": OpenRouterProvider,
    "gemini": GeminiProvider,
}


def get_provider(provider: str, api_key: str, model_string: str,
                 temperature: float, max_tokens: int) -> Provider:
    cls = _REGISTRY.get((provider or "").strip().lower())
    if cls is None:
        raise ConfigError(
            f"No provider adapter registered for '{provider}'. "
            f"Known: {', '.join(sorted(_REGISTRY))}."
        )
    return cls(api_key=api_key, model_string=model_string,
               temperature=temperature, max_tokens=max_tokens)