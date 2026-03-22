import re
from src.config import BLOCKED_TOPICS

BLOCKED_PATTERNS = [
    r"\b(buy|sell|short)\b.*\b(stock|share|crypto|bitcoin|eth)\b",
    r"\bguaranteed\b.*\b(returns?|profit|income)\b",
    r"\b(kill|murder|assault|firearm|gun|knife|bomb)\b",
    r"\b(sexy|nude|nsfw)\b",
    r"\bNFA\b",
    r"\bnot financial advice\b",
]


def is_safe(text: str) -> tuple[bool, str]:
    """Check if content passes safety filters.

    Returns (is_safe, reason) tuple.
    """
    lower = text.lower()

    # Check blocked topics
    for topic in BLOCKED_TOPICS:
        if topic.lower() in lower:
            return False, f"Contains blocked topic: '{topic}'"

    # Check regex patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lower):
            return False, f"Matches blocked pattern: '{pattern}'"

    # Check length
    if len(text) > 300:
        return False, "Content too long (>300 chars)"

    if len(text) < 10:
        return False, "Content too short (<10 chars)"

    return True, "OK"


def filter_caption(caption: str) -> tuple[bool, str]:
    """Check if a caption is safe to post."""
    lower = caption.lower()

    for topic in BLOCKED_TOPICS:
        if topic.lower() in lower:
            return False, f"Caption contains blocked topic: '{topic}'"

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lower):
            return False, f"Caption matches blocked pattern: '{pattern}'"

    return True, "OK"
