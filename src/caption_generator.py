import re

from src.config import YOUTUBE_CHANNEL_NAME
from src.llm import generate

# --- Instagram ---

HASHTAG_POOLS = {
    "wealth_building": ["#wealth", "#buildwealth", "#wealthmindset", "#moneymoves", "#financialgrowth"],
    "mindset": ["#mindset", "#growthmindset", "#winnermindset", "#mentalstrength", "#mindsetshift"],
    "discipline": ["#discipline", "#consistency", "#craftsmanship", "#noexcuses", "#showupdaily"],
    "investing": ["#investing", "#invest", "#smartmoney", "#financialliteracy", "#compounding"],
    "entrepreneurship": ["#entrepreneur", "#smallbusiness", "#ownersonly", "#business", "#buildsomething"],
    "autonomy": ["#ownyourtime", "#selfemployed", "#ownboss", "#debtfree", "#freedom"],
    "productivity": ["#productivity", "#efficiency", "#timemanagement", "#highperformance", "#focus"],
    "leadership": ["#leadership", "#leader", "#influence", "#executive", "#vision"],
    "stoicism": ["#stoicism", "#stoic", "#marcusaurelius", "#philosophy", "#innerpeace"],
    "self_improvement": ["#selfimprovement", "#bettereveryday", "#personalgrowth", "#characterbuilding", "#quietwork"],
}

# Brand hashtag derives from the channel name so a rename applies everywhere
UNIVERSAL_HASHTAGS = [
    "#" + YOUTUBE_CHANNEL_NAME.lower().replace(" ", ""),
    "#motivation",
    "#success",
]


def _clean_caption(text: str) -> str:
    """Strip wrapper artifacts the model copies from the examples.

    Even with an explicit instruction, models reproduce whatever shape they see:
    surrounding quotes, a trailing [ironic] label, or a paragraph explaining the
    choice. Cheaper to remove them here than to keep re-tuning the prompt.
    """
    text = text.strip()
    # Drop an explanation block introduced by a bracketed label
    text = re.split(r"\n\s*[\[(](?:IRONIC|SINCERE)", text, flags=re.I)[0]
    text = text.split("\n")[0].strip()
    text = re.sub(r"\s*[\[(](?:ironic|sincere)[^\])]*[\])]\s*$", "", text, flags=re.I)
    text = text.strip().strip('"').strip("'").strip()
    text = text.replace("*", "").replace("—", " - ").replace("–", " - ")
    return text.strip()


def generate_caption(quote_text: str, theme: str) -> str:
    """Generate an Instagram caption — a second beat, not a restatement.

    The previous version asked for "2-3 sentences expanding on the idea, ending
    with a thought-provoking question". That is engagement bait and it is exactly
    backwards: the reference accounts in this genre never expand and never ask.
    The caption TURNS on the image — undercuts it or doubles down on it — and the
    alternation between those two registers is what the voice actually is.
    """
    from src.content_generator import _load_canon

    canon = _load_canon()
    cap = canon.get("caption", {})
    human = "\n".join(f"  - {r}" for r in canon.get("human_voice", {}).get("rules", []))
    # Rendered WITHOUT quote marks or register labels around the caption: the
    # model copies whatever wrapper it sees, and labelled examples produced
    # captions like: "..." [ironic] followed by an explanation paragraph.
    examples = "\n\n".join(
        f'Line on image: {e["line"]}\nCaption:\n{e["caption"]}'
        for e in cap.get("examples", [])
    )
    banned = ", ".join(canon.get("forbidden_vocabulary", []))

    prompt = f"""Write ONE Instagram caption to sit under this line.

THE LINE ON THE IMAGE
"{quote_text}"

WHAT A CAPTION IS FOR
{cap.get("_why", "")}

EXAMPLES
{examples}

SOUNDING LIKE A PERSON
{human}

RULES
- Work out what the line is ABOUT before you write. Answer the human situation
  underneath it, not a noun it happens to contain. A line using "clothes" to talk
  about a broken promise is about the promise — a caption about gym memberships is
  answering the wrong word, and reads as a non-sequitur under the images.
- Under 120 characters. Often much shorter — four words can be the whole caption.
- Never restate the line. Never explain it. Never summarise it.
- Never end with a question. We do not farm comments.
- No emojis, no hashtags, no call to action, no "double tap if".
- Pick ONE register and commit to it:
    IRONIC  = dry, deadpan, understated. An aside muttered by someone who has
              seen this before. NOT relatable-meme, NOT self-deprecating
              millennial voice, NOT "me at 3am", NOT quirky.
    SINCERE = double down on the line and mean it. Still specific, still short.
- Output the caption text and nothing else. No quotation marks around it, no
  register label, no explanation of your choice, no markdown, no asterisks.
- Never use these words: {banned}
- Do not give specific financial advice.

Return only the caption."""

    caption = _clean_caption(generate(prompt, max_tokens=120))

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
    "autonomy": ["own your time", "work for yourself", "answer to nobody", "debt free", "self employed"],
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
- 1-2 sentences that expand on the idea with a strong opinion
- End with a SPECIFIC engagement question that makes people want to comment. NOT generic like "What do you think?" — instead ask something debatable:
  * "Agree or disagree?"
  * "What age did you figure this out?"
  * "Type 'DISCIPLINE' if this hit hard."
  * "Be honest. How much of your paycheck do you actually keep?"
- Masculine, direct tone
- NO emojis, NO hashtags in the description
- Do NOT give specific financial advice
- Keep it under 250 characters total

Return ONLY the description text."""

    desc = generate(prompt, max_tokens=300)
    # Clean up any emdashes/endashes the LLM sneaks in
    desc = desc.replace("—", " - ").replace("–", " - ")
    desc += f"\n\nSubscribe to {YOUTUBE_CHANNEL_NAME} for daily money motivation."

    # Visible hashtags — keep it to 3-5, relevant to theme
    theme_hashtags = {
        "wealth_building": "#wealth #money #success",
        "mindset": "#mindset #success #motivation",
        "discipline": "#discipline #motivation #grind",
        "investing": "#investing #money #finance",
        "entrepreneurship": "#entrepreneur #business #hustle",
        "autonomy": "#ownyourtime #selfemployed #wealth",
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
