import hashlib
import html
import json
import random
import requests
from pathlib import Path
from src.config import CONTENT_THEMES, DATA_DIR
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

POSTED_TITLES_PATH = DATA_DIR / "posted_titles.json"


def _load_posted_titles() -> list[str]:
    """Load all previously posted titles from the repo-tracked JSON file."""
    if POSTED_TITLES_PATH.exists():
        try:
            return json.loads(POSTED_TITLES_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_posted_title(title: str):
    """Append a new title to the posted titles file.

    Append-only and chronological. Never sort: generate_original_content reads
    the TAIL of this list as the "recently posted, do not repeat" sample, so
    sorting it would feed the LLM an alphabetical slice instead of recent work.
    Dedup keeps first-seen order rather than collapsing to a set.
    """
    titles = _load_posted_titles()
    titles.append(title)
    seen = set()
    ordered = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    POSTED_TITLES_PATH.write_text(json.dumps(ordered, indent=2))


# Overlap is measured on content words only. Titles here share a heavy common
# vocabulary ("you", "your", "money", "is"), and counting those made unrelated
# quotes look like duplicates — one real rejection was 6 shared words of which
# only 1 carried meaning.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "back", "be", "but", "by", "can",
    "cant", "do", "dont", "every", "for", "from", "get", "has", "have", "how",
    "in", "into", "is", "it", "its", "just", "like", "make", "makes", "more",
    "no", "not", "of", "on", "only", "or", "own", "so", "than", "that", "the",
    "them", "then", "they", "this", "to", "until", "up", "was", "what", "when",
    "who", "will", "with", "you", "youre", "your", "yourself",
}


def _normalize(text: str) -> str:
    """Lowercase, unescape HTML entities, strip punctuation."""
    text = html.unescape(text).lower()
    return "".join(c if c.isalnum() or c.isspace() else " " for c in text)


def _content_words(text: str) -> set[str]:
    """Meaning-carrying words, stopwords removed."""
    return {w for w in _normalize(text).split() if w and w not in STOPWORDS}


def _hook(text: str) -> str:
    """The first sentence — the part that has to stop the scroll."""
    return _normalize(html.unescape(text).split(".")[0]).strip()


# How far back the fuzzy-overlap check looks. Hook reuse is checked against ALL
# history (exact match, so it stays cheap and permanent), but content-word
# overlap only against this many recent posts. Without a window the guard gets
# monotonically stricter as history grows and would eventually reject every
# candidate, blowing the 8-attempt budget and killing the post outright.
# At 5 posts/day this is roughly a 2-month lookback.
OVERLAP_WINDOW = 300


def _is_too_similar(new_text: str, existing_titles: list[str], threshold: float = 0.6) -> bool:
    """Check if new_text is too similar to any existing title.

    Two checks:
      1. Exact hook reuse, against all history. The first sentence is the whole
         ballgame on Shorts — a shared hook reads as a repost even when the
         payoff differs.
      2. Content-word overlap above `threshold` against the shorter side,
         limited to the most recent OVERLAP_WINDOW posts.
    """
    new_words = _content_words(new_text)
    if not new_words:
        return True

    new_hook = _hook(new_text)
    if new_hook and any(new_hook == _hook(t) for t in existing_titles):
        return True

    recent = existing_titles[-OVERLAP_WINDOW:]
    for title in recent:
        existing_words = _content_words(title)
        if not existing_words:
            continue
        # Jaccard-like overlap: intersection / smaller set
        overlap = len(new_words & existing_words)
        smaller = min(len(new_words), len(existing_words))
        if smaller > 0 and overlap / smaller > threshold:
            return True
    return False


def get_weighted_theme() -> str:
    scores = get_theme_scores()

    # Fall back to theme_scores.json if DB is empty (e.g. GitHub Actions)
    if not scores:
        json_path = DATA_DIR / "theme_scores.json"
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


def generate_original_content(theme: str, inspiration: dict | None = None) -> dict | None:
    """Use LLM to generate original quote-style content."""
    inspiration_text = ""
    if inspiration:
        inspiration_text = f"\nUse this as loose inspiration (do NOT copy): \"{inspiration.get('text', '')}\""

    theme_desc = THEME_LABELS.get(theme, theme)

    # Load posted titles for anti-repetition
    posted_titles = _load_posted_titles()

    # Show LLM a sample of recent titles to avoid
    avoid_sample = posted_titles[-40:] if len(posted_titles) > 40 else posted_titles
    avoid_block = ""
    if avoid_sample:
        titles_str = "\n".join(f"  - {t}" for t in avoid_sample)
        avoid_block = f"""
PREVIOUSLY POSTED (do NOT repeat these concepts, phrases, or structures):
{titles_str}

Your quote MUST be completely different from ALL of the above. Different concept, different angle, different words. If you catch yourself writing something similar, start over."""

    # Pick a random hook structure to force variety
    hook_styles = [
        "a specific dollar amount or number that shocks (e.g. '$7 a day becomes $2.1 million')",
        "a direct 'you' accusation that stings (e.g. 'You're subsidizing someone else's dream')",
        "a counterintuitive claim that sounds wrong but is true (e.g. 'Saving money is making you poor')",
        "a comparison between two things (e.g. 'A gym membership costs $50. Diabetes costs $500,000')",
        "a time-based urgency (e.g. 'Every hour you delay costs you $11 in lost compound growth')",
        "a status/identity challenge (e.g. 'Rich people don't have savings accounts')",
        "a vivid scenario (e.g. 'Your future self is watching you scroll right now')",
    ]
    chosen_hook = random.choice(hook_styles)

    prompt = f"""Generate a single powerful, original quote about {theme_desc} for a finance/motivation brand called "MASTERING MONEY".
{inspiration_text}
{avoid_block}

HOOK STYLE FOR THIS QUOTE: Use {chosen_hook}

Rules:
- EXACTLY 2 sentences. Both end with a period.
- THE FIRST SENTENCE IS THE HOOK. It must stop someone mid-scroll in under 8 words.
- The second sentence delivers a SPECIFIC payoff — a concrete insight, consequence, or hard truth. No vague advice.
- TOTAL LENGTH: 60-120 characters. Shorter is better. Every word must earn its place.
- Masculine, direct, zero-fluff tone.
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

    # --- Dedup check 1: exact hash ---
    content_hash = hashlib.sha256(text.lower().encode()).hexdigest()
    if content_exists(content_hash):
        print("    (rejected: exact duplicate)")
        return None

    # --- Dedup check 2: similarity to posted titles ---
    if _is_too_similar(text, posted_titles):
        print(f"    (rejected: too similar to existing)")
        return None

    save_content_hash(content_hash)
    return {"text": text, "theme": theme, "source": "original"}


def generate_content(post_type: str = "feed") -> dict | None:
    """Generate content for a post. Tries multiple strategies with dedup."""
    theme = get_weighted_theme()

    # Strategy 1: Try with a fetched quote as inspiration
    quote = fetch_quote()
    if quote:
        result = generate_original_content(theme, inspiration=quote)
        if result:
            return result

    # Strategy 2: Generate purely original content (more attempts for dedup rejections)
    for attempt in range(8):
        # Rotate themes if we keep getting rejected (stuck in a narrow concept space)
        if attempt >= 4:
            theme = get_weighted_theme()
        result = generate_original_content(theme)
        if result:
            return result

    print("  WARNING: Could not generate unique content after 8 attempts")
    return None
