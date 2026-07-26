import hashlib
import html
import json
import random
import re
import requests
from pathlib import Path
from src.config import (
    CANDIDATES_PER_POST,
    CONTENT_THEMES,
    DATA_DIR,
    HOOK_STYLES,
    JUDGE_MODEL,
)
from src.llm import generate
from src.database import content_exists, save_content_hash, get_theme_scores

THEME_LABELS = {
    "wealth_building": "building wealth and financial growth",
    "mindset": "mindset and mental toughness",
    "discipline": "discipline and consistency",
    "investing": "investing and smart money moves",
    "entrepreneurship": "entrepreneurship and building businesses",
    # Label deliberately avoids the phrase "financial freedom" — the canon bans it
    # as dead from overuse, and asking for a theme in words the model may not use
    # is a contradiction that costs generations. The KEY is unchanged so the
    # theme's scoring history survives.
    "financial_freedom": "owning your own time and answering to nobody",
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


def _load_scores_json(filename: str) -> dict[str, float]:
    """Load a learned score file. Empty dict if absent or malformed.

    An empty result means every option falls back to weight 1.0, i.e. uniform
    sampling — the correct cold-start for a dial with no data yet.
    """
    path = DATA_DIR / filename
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return {k: float(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return {}


def _weighted_pick(options: list[str], scores: dict[str, float]) -> str:
    """Sample one option, weighted by learned score (default 1.0)."""
    weights = [max(scores.get(o, 1.0), 0.01) for o in options]
    return random.choices(options, weights=weights, k=1)[0]


def get_weighted_theme() -> str:
    scores = get_theme_scores()

    # Fall back to theme_scores.json if DB is empty (e.g. GitHub Actions)
    if not scores:
        scores = _load_scores_json("theme_scores.json")

    return _weighted_pick(CONTENT_THEMES, scores)


CANON_PATH = DATA_DIR / "voice_canon.json"


def _load_canon() -> dict:
    """The account's voice, as exemplars. Empty dict if missing — the form rules
    still apply, we just lose the aesthetic guidance rather than the whole post."""
    try:
        return json.loads(CANON_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"    (canon unreadable: {type(e).__name__} — falling back to form rules only)")
        return {}


def _parse_candidates(raw: str) -> list[str]:
    """Pull numbered lines out of the model's reply.

    Tolerant on purpose: numbering style drifts between models and a strict
    parser would throw away a whole usable batch over a stray bullet.
    """
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip a leading "1.", "1)", "-", "*" if present
        line = re.sub(r"^\s*(?:\d+\s*[.)\-:]|[-*•])\s*", "", line).strip()
        line = line.strip('"').strip("'").strip()
        # A candidate is two sentences in the target length band
        if 40 <= len(line) <= 200 and line.count(".") >= 2:
            out.append(line)
    return out


def _judge_candidates(candidates: list[str], canon: dict) -> tuple[str, int, str]:
    """Score candidates against the canon and return the best.

    Separate cheap model on purpose: this is scoring against explicit criteria,
    not writing, so it wants consistency rather than brilliance. On any failure
    it falls back to the first candidate — a judge outage should cost us the
    choice, never the post.
    """
    if len(candidates) == 1:
        return candidates[0], 5, "only one survivor, no choice to make"

    numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates))
    tests = "\n".join(f"  - {t}" for t in canon.get("register_test", []))
    prompt = f"""Pick the strongest line for a channel that argues character beats calculation.

THE PRINCIPLE
{canon.get("principle", "")}

JUDGE AGAINST THIS
{tests}
  - Would a person stop scrolling for it, or is it merely agreeable?
  - Has it been said a thousand times already? Familiar phrasing loses.

CANDIDATES
{numbered}

Reply in exactly this format and nothing else:
PICK: <number>
SCORE: <0-10 for the line you picked>
REASON: <one short clause>"""

    try:
        from src.llm import generate_with_model

        reply = generate_with_model(JUDGE_MODEL, prompt, max_tokens=120)
    except Exception as e:
        print(f"    (judge failed: {type(e).__name__} — taking first candidate)")
        return candidates[0], 5, "judge unavailable"

    pick, score, reason = 1, 5, "unparsed"
    for line in reply.splitlines():
        line = line.strip()
        up = line.upper()
        if up.startswith("PICK:"):
            d = "".join(ch for ch in line.split(":", 1)[1] if ch.isdigit())
            if d:
                pick = max(1, min(len(candidates), int(d[:2])))
        elif up.startswith("SCORE:"):
            d = "".join(ch for ch in line.split(":", 1)[1] if ch.isdigit())
            if d:
                score = max(0, min(10, int(d[:2])))
        elif up.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()[:100]
    return candidates[pick - 1], score, reason


def get_weighted_hook() -> str:
    """Pick a hook archetype key, weighted by learned performance.

    Previously this was random.choice over prose strings with no key, no record,
    and no scoring — so the dial that the data suggests matters most was pure
    noise. Falls back to uniform until hook_scores.json has data.
    """
    return _weighted_pick(list(HOOK_STYLES.keys()), _load_scores_json("hook_scores.json"))


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

    # Load posted titles for anti-repetition — used by the CODE guard only.
    #
    # The old prompt pasted 40 previous titles in as a "do not repeat" block.
    # That was 637 tokens of the register we are replacing, shipped on every
    # call: telling a model not to repeat something still teaches it that this is
    # the kind of thing written here, and it was the largest block of aesthetic
    # instruction in the prompt. Dedup and voice are different jobs — dedup lives
    # in _is_too_similar() against all history, voice lives in the canon below.
    posted_titles = _load_posted_titles()

    # Pick a hook archetype, weighted by learned conversion performance
    hook_style = get_weighted_hook()
    chosen_hook = HOOK_STYLES[hook_style]

    canon = _load_canon()
    good = "\n".join(f'  "{e["line"]}"\n     -> {e["why"]}' for e in canon.get("good", []))
    bad = "\n".join(f'  "{e["line"]}"\n     -> {e["why"]}' for e in canon.get("bad", []))
    tests = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(canon.get("register_test", [])))
    banned = ", ".join(canon.get("forbidden_vocabulary", []))

    prompt = f"""Write {CANDIDATES_PER_POST} candidate lines about {theme_desc} for a channel that argues character beats calculation.
{inspiration_text}

THE PRINCIPLE
{canon.get("principle", "")}

WHAT WE ARE AGAINST
{canon.get("enemy", "")}

LINES THAT WORK, AND WHY
{good}

LINES THAT FAIL, AND WHY
{bad}

TEST EVERY LINE AGAINST THIS
{tests}

HOOK STYLE FOR THIS BATCH: {chosen_hook}

FORM
- EXACTLY 2 sentences. Both end with a period.
- The FIRST sentence is the hook: it stops a thumb in under 8 words.
- The SECOND lands a specific consequence. Never vague advice.
- 60-120 characters total. Shorter is stronger.
- No emdashes, endashes, colons or semicolons. Periods only.
- No hashtags, no emojis, no quotation marks, no attribution.
- Never name a specific stock, coin or product.
- Never use these words: {banned}

The {CANDIDATES_PER_POST} candidates must differ in STRUCTURE, not just wording. If two of
them could be rewrites of each other, replace one. Reach for the strange, exact
image over the safe, familiar phrasing — a line nobody has written yet beats a
line that is merely correct.

Return exactly {CANDIDATES_PER_POST} lines, one per line, numbered 1. to {CANDIDATES_PER_POST}. Nothing else."""

    raw = generate(prompt, max_tokens=100 + 60 * CANDIDATES_PER_POST)
    candidates = _parse_candidates(raw)
    if not candidates:
        print("    (no parseable candidates)")
        return None

    # Dedup in code against all history, then let the judge choose among survivors
    survivors = []
    for c in candidates:
        h = hashlib.sha256(c.lower().encode()).hexdigest()
        if content_exists(h) or _is_too_similar(c, posted_titles):
            continue
        survivors.append(c)

    print(f"    {len(candidates)} candidates, {len(survivors)} survived dedup")
    if not survivors:
        return None

    text, judge_score, judge_reason = _judge_candidates(survivors, canon)
    print(f'    picked {judge_score}/10 — {judge_reason}')
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
    # hook_style rides along so the poster can record it against the video_id
    return {
        "text": text, "theme": theme, "hook_style": hook_style,
        "source": "original", "judge_score": judge_score,
    }


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
