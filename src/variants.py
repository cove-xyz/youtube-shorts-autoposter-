"""Attribution log: which generation choices produced which published video.

The learning loop can only optimize variables it can attribute to outcomes. The
YouTube API tells us how video X performed; only this file can tell us that
video X used the `future_self` hook at 10 seconds with no voiceover. Without it,
every new variable is unlearnable no matter how it is sampled — which is why
hook style was random for months while theme scoring got all the attention.

Design notes:
  - Keyed by YouTube video_id so analytics can join directly against API rows.
  - Append-only, chronological, committed to the repo. The SQLite DB is
    ephemeral in GitHub Actions, so it cannot hold cross-run learning state.
  - Records are open-ended dicts. Adding a new tracked variable means writing
    one more key here and reading it in analytics — no migration.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import DATA_DIR, TIMEZONE

VARIANTS_PATH = DATA_DIR / "post_variants.json"


def load_variants() -> list[dict]:
    """All recorded variants, oldest first. Empty list if none yet."""
    if VARIANTS_PATH.exists():
        try:
            data = json.loads(VARIANTS_PATH.read_text())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def variants_by_video_id() -> dict[str, dict]:
    """Lookup table for joining against YouTube Analytics rows."""
    return {v["video_id"]: v for v in load_variants() if v.get("video_id")}


def record_variant(video_id: str, **fields) -> None:
    """Append one published video's generation choices.

    Append-only and never sorted, matching posted_titles.json. Re-recording an
    existing video_id updates that record in place rather than duplicating it.
    """
    if not video_id:
        return

    try:
        now = datetime.now(ZoneInfo(TIMEZONE)).isoformat(timespec="seconds")
    except Exception:
        now = datetime.now().isoformat(timespec="seconds")

    record = {"video_id": video_id, "posted_at": now, **fields}

    variants = load_variants()
    for i, existing in enumerate(variants):
        if existing.get("video_id") == video_id:
            variants[i] = {**existing, **record}
            break
    else:
        variants.append(record)

    VARIANTS_PATH.write_text(json.dumps(variants, indent=2))
