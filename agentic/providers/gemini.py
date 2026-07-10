from .base import Provider
from ..errors import ConnectionErr, ProcessingError


class GeminiProvider(Provider):
    def run(self, rendered: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ConnectionErr("google-genai SDK is not installed.")

        try:
            client = genai.Client(api_key=self.api_key)
            resp = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=rendered,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                ),
            )
        except Exception as e:
            msg = str(e).lower()
            if any(t in msg for t in ("api key", "permission", "401", "403")):
                raise ConnectionErr("Gemini rejected the API key.")
            if any(t in msg for t in ("quota", "rate", "429")):
                raise ConnectionErr("Gemini quota/rate limit reached. Try again shortly.")
            raise ConnectionErr(f"Could not reach Gemini: {e}")

        text = getattr(resp, "text", None)
        if not text:
            raise ProcessingError("Gemini returned an empty response.")
        return text