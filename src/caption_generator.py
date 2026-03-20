from src.config import YOUTUBE_CHANNEL_NAME
from src.llm import generate

# --- Instagram ---

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
    prompt = f"""Write an Instagram caption for this quote posted by a finance/motivation account called "MASTERING MONEY":

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

Return ONLY the caption text."""

    caption = generate(prompt, max_tokens=300)

    # Add hashtags
    theme_tags = HASHTAG_POOLS.get(theme, [])[:5]
    all_tags = UNIVERSAL_HASHTAGS + theme_tags
    hashtag_str = " ".join(all_tags[:8])

    return f"{caption}\n\n{hashtag_str}"


def generate_story_caption(quote_text: str) -> str:
    """Generate a shorter caption for stories."""
    prompt = f"""Write a one-sentence reaction or expansion for this quote, for an Instagram story:

Quote: "{quote_text}"

Rules:
- One punchy sentence
- Direct, masculine tone
- Under 80 characters
- NO emojis, NO hashtags

Return ONLY the sentence."""

    return generate(prompt, max_tokens=100)


# --- YouTube ---

YOUTUBE_TAG_POOLS = {
    "wealth_building": ["wealth building", "build wealth", "money mindset", "financial growth", "rich mindset"],
    "mindset": ["mindset", "growth mindset", "mental toughness", "winner mindset", "success mindset"],
    "discipline": ["discipline", "consistency", "self discipline", "daily habits", "no excuses"],
    "investing": ["investing", "smart money", "financial literacy", "compound interest", "money tips"],
    "entrepreneurship": ["entrepreneur", "business motivation", "startup mindset", "hustle", "CEO mindset"],
    "financial_freedom": ["financial freedom", "passive income", "FIRE movement", "debt free", "money freedom"],
    "productivity": ["productivity", "time management", "high performance", "efficiency", "peak performance"],
    "leadership": ["leadership", "leader mindset", "influence", "executive mindset", "how to lead"],
    "stoicism": ["stoicism", "stoic quotes", "marcus aurelius", "philosophy", "emotional control"],
    "self_improvement": ["self improvement", "level up", "personal growth", "better every day", "self development"],
}

YOUTUBE_UNIVERSAL_TAGS = [
    "Shorts", "motivation", "money motivation", "success",
    "mastering money", "motivational quotes", "finance motivation",
]


def generate_youtube_description(quote_text: str, theme: str) -> str:
    """Generate a YouTube Shorts description optimized for search and engagement."""
    prompt = f"""Write a YouTube Shorts description for this motivational quote by the channel "{YOUTUBE_CHANNEL_NAME}":

Quote: "{quote_text}"
Theme: {theme}

Rules:
- 2-3 sentences that expand on the quote's meaning
- First sentence should hook the reader — start with a bold statement or question
- End with a clear call to action: "Subscribe for daily motivation" or "Follow for more"
- Masculine, direct tone
- NO emojis, NO hashtags in the description
- Do NOT give specific financial advice
- Keep it under 300 characters total

Return ONLY the description text."""

    desc = generate(prompt, max_tokens=400)
    desc += f"\n\nSubscribe to {YOUTUBE_CHANNEL_NAME} for daily motivation."

    # Visible hashtags — keep it to 3-5, relevant to theme
    theme_hashtags = {
        "wealth_building": "#wealth #money #success",
        "mindset": "#mindset #success #motivation",
        "discipline": "#discipline #motivation #grind",
        "investing": "#investing #money #finance",
        "entrepreneurship": "#entrepreneur #business #hustle",
        "financial_freedom": "#financialfreedom #money #wealth",
        "productivity": "#productivity #success #focus",
        "leadership": "#leadership #success #mindset",
        "stoicism": "#stoicism #mindset #discipline",
        "self_improvement": "#selfimprovement #motivation #growth",
    }
    hashtags = theme_hashtags.get(theme, "#motivation #success #money")
    desc += f"\n\n#shorts {hashtags}"
    return desc


def generate_youtube_tags(theme: str) -> list[str]:
    """Return YouTube tags for a Short based on its theme."""
    theme_tags = YOUTUBE_TAG_POOLS.get(theme, [])
    all_tags = YOUTUBE_UNIVERSAL_TAGS + theme_tags
    return all_tags[:15]
