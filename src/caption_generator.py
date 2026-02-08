import anthropic
from src.config import ANTHROPIC_API_KEY

HASHTAG_POOLS = {
    "wealth_building": ["#wealth", "#buildwealth", "#wealthmindset", "#moneymoves", "#financialgrowth"],
    "mindset": ["#mindset", "#growthmindset", "#winnermindset", "#mentalstrength", "#mindsetshift"],
    "discipline": ["#discipline", "#consistency", "#grindmode", "#noexcuses", "#dailygrind"],
    "investing": ["#investing", "#invest", "#smartmoney", "#financialliteracy", "#compounding"],
    "entrepreneurship": ["#entrepreneur", "#startup", "#hustle", "#business", "#ceo"],
    "financial_freedom": ["#financialfreedom", "#passiveincome", "#fire", "#debtfree", "#freedom"],
    "productivity": ["#productivity", "#efficiency", "#timemanagement", "#highperformance", "#focus"],
    "leadership": ["#leadership", "#leader", "#influence", "#executive", "#vision"],
    "stoicism": ["#stoicism", "#stoic", "#marcusaurelius", "#philosophy", "#innerpeace"],
    "self_improvement": ["#selfimprovement", "#levelup", "#bettereveryday", "#personalgrowth", "#evolve"],
}

UNIVERSAL_HASHTAGS = ["#masteringmoney", "#motivation", "#success"]


def generate_caption(quote_text: str, theme: str) -> str:
    """Generate an Instagram caption for a quote."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": f"""Write an Instagram caption for this quote posted by a finance/motivation account called "MASTERING MONEY":

Quote: "{quote_text}"
Theme: {theme}

Rules:
- 2-3 sentences expanding on the idea
- End with a thought-provoking question OR a direct call to action
- Masculine, direct, motivational tone
- NO emojis
- NO hashtags (those get added separately)
- Do NOT give specific financial advice
- Keep it under 200 characters total

Return ONLY the caption text.""",
            }
        ],
    )

    caption = message.content[0].text.strip()

    # Add hashtags
    theme_tags = HASHTAG_POOLS.get(theme, [])[:5]
    all_tags = UNIVERSAL_HASHTAGS + theme_tags
    hashtag_str = " ".join(all_tags[:8])

    return f"{caption}\n\n{hashtag_str}"


def generate_story_caption(quote_text: str) -> str:
    """Generate a shorter caption for stories (used as alt text / overlay if needed)."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": f"""Write a one-sentence reaction or expansion for this quote, for an Instagram story:

Quote: "{quote_text}"

Rules:
- One punchy sentence
- Direct, masculine tone
- Under 80 characters
- NO emojis, NO hashtags

Return ONLY the sentence.""",
            }
        ],
    )

    return message.content[0].text.strip()
