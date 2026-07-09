import requests
from .base import Provider
from ..errors import ConnectionErr, ProcessingError

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT = 120


class OpenRouterProvider(Provider):
    def run(self, rendered: str) -> str:
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model_string,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": rendered}],
                },
                timeout=TIMEOUT,
            )
        except requests.Timeout:
            raise ConnectionErr("Timed out connecting to OpenRouter.")
        except requests.ConnectionError:
            raise ConnectionErr("Could not connect to OpenRouter — check network.")
        except requests.RequestException as e:
            raise ConnectionErr(f"OpenRouter request failed: {e}")

        if resp.status_code == 401:
            raise ConnectionErr("OpenRouter rejected the API key (401).")
        if resp.status_code == 429:
            raise ConnectionErr("OpenRouter rate limit reached (429). Try again shortly.")
        if resp.status_code >= 400:
            raise ConnectionErr(f"OpenRouter returned {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as e:
            raise ProcessingError(f"Unexpected OpenRouter response shape: {e}")