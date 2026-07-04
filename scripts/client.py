# """Thin Gemini client. Reads the API token from settings/env and makes a single
# deterministic, schema-constrained call.

# Reproducibility levers live here: temperature=0 and a hard response schema so the
# SHAPE of the output never varies even if a word does. The VALUES are kept stable
# by extracting raw figures (the model returns 'HR 0.61 (95% CI ...)' verbatim in
# `raw`) and letting downstream code canonicalise them.
# """

# import json
# import os

# from django.conf import settings

# GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


# def _api_key():
#     key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")
#     if not key:
#         raise RuntimeError("GEMINI_API_KEY is not set (settings.GEMINI_API_KEY or env).")
#     return key


# def _model():
#     # Set settings.GEMINI_MODEL - the best models are the latest ones
#     return getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash")


# def call_gemini(system_text, user_text, response_schema, *, timeout=60):
#     """One deterministic call. Returns the parsed JSON object (per response_schema)."""
#     import requests  # local import so the module imports even if requests is absent

#     url = GEMINI_ENDPOINT.format(model=_model())
#     payload = {
#         "systemInstruction": {"parts": [{"text": system_text}]},
#         "contents": [{"role": "user", "parts": [{"text": user_text}]}],
#         "generationConfig": {
#             "temperature": 0,
#             "topP": 0,
#             "responseMimeType": "application/json",
#             "responseSchema": response_schema,
#         },
#     }
#     resp = requests.post(url, params={"key": _api_key()}, json=payload, timeout=timeout)
#     resp.raise_for_status()
#     body = resp.json()
#     try:
#         text = body["candidates"][0]["content"]["parts"][0]["text"]
#     except (KeyError, IndexError) as exc:
#         raise RuntimeError(f"Unexpected Gemini response shape: {body}") from exc
#     return json.loads(text)


"""Thin Gemini client (official google-genai SDK). Reads the API token from
settings/env and makes a single deterministic, schema-constrained call.

Reproducibility levers live here: temperature=0 and a hard response schema so the
SHAPE of the output never varies even if a word does. The VALUES are kept stable
by extracting raw figures (the model returns 'HR 0.61 (95% CI ...)' verbatim in
`raw`) and letting downstream code canonicalise them.


"""

import json
import os

from django.conf import settings
from google import genai
from google.genai import types

_client = None
 
 
def _api_key():
    key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set (settings.GEMINI_API_KEY or env).")
    return key
 
 
def _model():
    return getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash")
 
 
def _temperature():
    # Higher -> more natural explanations
    # runs. The schema + cache still keep things stable. Tune via settings.
    return float(getattr(settings, "GEMINI_TEMPERATURE", 0.8))
 
 
def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=_api_key())
    return _client
 
 
def call_gemini(system_text, user_text, response_schema, *, timeout=60):
    """One schema-constrained call. Returns the parsed JSON object (per response_schema)."""
    config = types.GenerateContentConfig(
        system_instruction=system_text,
        temperature=_temperature(),
        response_mime_type="application/json",
        response_schema=response_schema,
        http_options=types.HttpOptions(timeout=timeout * 1000),  # SDK expects ms
    )
    response = _get_client().models.generate_content(
        model=_model(),
        contents=user_text,
        config=config,
    )
    text = response.text
    if not text:
        # e.g. a safety block or truncation — surface the candidates so it's debuggable
        raise RuntimeError(f"Empty Gemini response (finish reason: {response.candidates})")
    return json.loads(text)