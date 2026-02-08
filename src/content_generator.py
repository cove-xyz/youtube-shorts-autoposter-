import hashlib
import random
import requests
import anthropic
from src.config import ANTHROPIC_API_KEY, CONTENT_THEMES
from src.database import content_exists, save_content_hash, get_theme_scores


def get_weighted_theme() -> str:
    scores = get_theme_scores()
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
    """Use Claude to generate original quote-style content."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    inspiration_text = ""
    if inspiration:
        inspiration_text = f"\nUse this as loose inspiration (do NOT copy): \"{inspiration.get('text', '')}\""

    theme_labels = {
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

    theme_desc = theme_labels.get(theme, theme)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": f"""Generate a single powerful, original quote about {theme_desc} for a finance/motivation Instagram account called "MASTERING MONEY".
{inspiration_text}

Rules:
- Must be 1-2 sentences, punchy and memorable
- Masculine, direct, no-fluff motivational tone
- Think: something a successful CEO or investor would say
- NO attribution to anyone — this is original content
- NO hashtags, NO emojis
- Do NOT give specific financial advice or mention specific stocks/crypto
- Maximum 120 characters ideal, 180 characters absolute max

Return ONLY the quote text, nothing else.""",
            }
        ],
    )

    text = message.content[0].text.strip().strip('"').strip("'")

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
