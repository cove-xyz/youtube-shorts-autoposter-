"""Centralized LLM client. Routes through OpenRouter for cost efficiency.

OpenRouter is an OpenAI-compatible gateway — we use the openai SDK pointed
at their base URL. This lets us pick any model (DeepSeek, Claude, Gemini, etc.)
and switch with a single env var.

Cost comparison per Short (~800 tokens):
  DeepSeek V3:    ~$0.0003   (best value)
  Gemini Flash:   ~$0.0004
  Claude Haiku:   ~$0.003
  Claude Sonnet:  ~$0.01
"""

import time

from openai import OpenAI
from src.config import OPENROUTER_API_KEY, LLM_MODEL

# Tried in order when the primary model is rate-limited or a provider errors.
# Upstream DeepSeek capacity is the usual culprit, so the first fallback is a
# different vendor rather than another DeepSeek route.
# Fallbacks are deliberately different VENDORS, not different routes to the same
# one. The Jul 18 post was lost because every upstream provider for a single
# DeepSeek model was rate-limited at once — a same-vendor fallback would not have
# helped. Kimi is Moonshot, Haiku is Anthropic.
FALLBACK_MODELS = [
    "moonshotai/kimi-k3",
    "anthropic/claude-haiku-4.5",
]

MAX_ATTEMPTS_PER_MODEL = 3


def _get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys"
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


def _try_model(client: OpenAI, model: str, prompt: str, max_tokens: int) -> str | None:
    """Attempt one model with exponential backoff. None if it never succeeds."""
    for attempt in range(MAX_ATTEMPTS_PER_MODEL):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip()
            print(f"    ({model} returned empty content)")
        except Exception as e:
            wait = 2 ** attempt
            print(f"    ({model} attempt {attempt + 1}/{MAX_ATTEMPTS_PER_MODEL} failed: {type(e).__name__})")
            if attempt < MAX_ATTEMPTS_PER_MODEL - 1:
                time.sleep(wait)
    return None


def generate_with_model(model: str, prompt: str, max_tokens: int = 300) -> str:
    """Call one specific model, no fallback chain.

    Used by the judge, which must run on a known cheap model rather than
    inheriting whatever the writer is set to.
    """
    result = _try_model(_get_client(), model, prompt, max_tokens)
    if result is None:
        raise RuntimeError(f"{model} failed after {MAX_ATTEMPTS_PER_MODEL} attempts")
    return result


def generate(prompt: str, max_tokens: int = 300) -> str:
    """Send a prompt to the LLM and return the text response.

    Retries the primary model with backoff, then walks the fallback list.
    A scheduled post slot is worth more than strict model consistency —
    losing the slot entirely costs a day of reach.
    """
    client = _get_client()

    for model in [LLM_MODEL, *FALLBACK_MODELS]:
        result = _try_model(client, model, prompt, max_tokens)
        if result:
            if model != LLM_MODEL:
                print(f"    (used fallback model: {model})")
            return result

    raise RuntimeError(
        f"All models failed after retries: {[LLM_MODEL, *FALLBACK_MODELS]}"
    )
