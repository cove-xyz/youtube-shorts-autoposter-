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

from openai import OpenAI
from src.config import OPENROUTER_API_KEY, LLM_MODEL


def _get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Get one at https://openrouter.ai/keys"
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


def generate(prompt: str, max_tokens: int = 300) -> str:
    """Send a prompt to the LLM and return the text response."""
    client = _get_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()
