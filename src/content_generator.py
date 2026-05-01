import hashlib
import json
import random
import requests
from pathlib import Path
from src.config import CONTENT_THEMES
from src.llm import generate
from src.database import content_exists, save_content_hash, get_theme_scores

THEME_LABELS = {
    "wealth_building": "building wealth and financial growth",
    "mindset": "mindset and mental toughness",
    "discipline": "discipline and consistency",
    "investing": "investing and smart money moves",
    "entrepreneurship": "entrepreneurship and building businesses",
    "financial_freedom": "financial freedom and independence",
    "productivity": "productivity and peak performance",
    "leadership": "leadership and influence",
    "stoicism": "stoic philosophy and emotional control",
    "self_improvement": "self-improvement and personal growth",
}


def get_weighted_theme() -> str:
    scores = get_theme_scores()

    # Fall back to theme_scores.json if DB is empty (e.g. GitHub Actions)
    if not scores:
        json_path = Path(__file__).resolve().parent.parent / "data" / "theme_scores.json"
        if json_path.exists():
            scores = json.loads(json_path.read_text())

    themes = CONTENT_THEMES
    weights = [scores.get(t, 1.0) for t in themes]
    return random.choices(themes, weights=weights, k=1)[0]


def fetch_quote() -> dict | None:
    """Fetch a quote from the Quotable API."""
    try:
        tags = "wisdom|motivational|inspirational|success|business"
        resp = requests.get(
            f"https://api.quotable.io/random?tags={tags}", timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"text": data["content"], "author": data["author"], "source": "quotable"}
    except Exception:
        pass
    return None


def fetch_financial_insight() -> dict | None:
    """Fetch a financial news headline to inspire content."""
    try:
        resp = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "topics": "financial_markets", "apikey": "demo"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            articles = data.get("feed", [])
            if articles:
                article = random.choice(articles[:10])
                return {
                    "text": article.get("title", ""),
                    "summary": article.get("summary", ""),
                    "source": "alphavantage",
                }
    except Exception:
        pass
    return None


def generate_original_content(theme: str, inspiration: dict | None = None) -> dict | None:
    """Use LLM to generate original quote-style content."""
    inspiration_text = ""
    if inspiration:
        inspiration_text = f"\nUse this as loose inspiration (do NOT copy): \"{inspiration.get('text', '')}\""

    theme_desc = THEME_LABELS.get(theme, theme)

    prompt = f"""Generate a single powerful, original quote about {theme_desc} for a finance/motivation brand called "MASTERING MONEY".
{inspiration_text}

Rules:
- EXACTLY 2 sentences. Both end with a period.
- THE FIRST SENTENCE IS THE HOOK. It must be SHORT (under 10 words), specific, and create instant tension. The viewer decides in 0.5 seconds whether to keep watching.
- BANNED hook patterns (overused, YouTube ignores these now):
  * "Most people..." — NEVER start with this. It's the #1 most saturated opener on Shorts.
  * "Everyone wants..." / "Nobody tells you..." / "They don't want you to know..."
  * Any generic opener that could apply to anything. Be SPECIFIC.
- GREAT hook patterns (use these):
  * A specific number or stat: "Your $10,000 savings lost $800 this year."
  * A direct accusation: "You're broke because you're comfortable."
  * A counterintuitive claim: "The rich don't budget."
  * A provocative question framed as a statement: "Saving money is making you poor."
  * Name a specific pain: "That $7 latte is a $2 million retirement decision."
- The second sentence delivers a SPECIFIC payoff or hard truth. It should make the viewer want to SHARE this with someone. Avoid vague advice like "master your choices" — instead give a concrete insight or consequence.
- Masculine, direct, zero-fluff tone. Write like someone who has earned the right to say this.
- KEEP IT SHORT. Under 120 characters total is ideal. The best-performing Shorts quotes are punchy, not wordy. Every word must earn its place.
- NO emdashes (—), NO endashes (–), NO dashes connecting clauses
- NO colons or semicolons. Use periods instead.
- NO attribution. This is original content.
- NO hashtags, NO emojis, NO quotation marks
- Do NOT give specific financial advice or mention specific stocks/crypto

Return ONLY the quote text, nothing else."""

    text = generate(prompt, max_tokens=100)
    text = text.strip().strip('"').strip("'")
    # Enforce: replace any emdashes/endashes the LLM sneaks in
    text = text.replace("—", ".").replace("–", ".").replace(" . ", ". ")
    # If LLM returned multiple lines/quotes, take only the first meaningful one
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        text = lines[0].strip().strip('"').strip("'")

    content_hash = hashlib.sha256(text.lower().encode()).hexdigest()
    if content_exists(content_hash):
        return None

    save_content_hash(content_hash)
    return {"text": text, "theme": theme, "source": "original"}


def generate_content(post_type: str = "feed") -> dict | None:
    """Generate content for a post. Tries multiple strategies."""
    theme = get_weighted_theme()

    # Strategy 1: Try with a fetched quote as inspiration
    quote = fetch_quote()
    if quote:
        result = generate_original_content(theme, inspiration=quote)
        if result:
            return result

    # Strategy 2: Try with financial news inspiration
    news = fetch_financial_insight()
    if news:
        result = generate_original_content(theme, inspiration=news)
        if result:
            return result

    # Strategy 3: Generate purely original content
    for _ in range(3):
        result = generate_original_content(theme)
        if result:
            return result

    return None
