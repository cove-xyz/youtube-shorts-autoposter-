"""Scheduled carousel publishing.

Runs hours before the target slot rather than posting immediately. Two reasons:

  * Instagram feed engagement is not flat across the day, so the post should land
    when people are actually looking rather than whenever a cron happened to fire.
  * The gap between generating and publishing IS the review window. Four generated
    photographs, a generated line and a generated caption going straight to the
    grid unseen is the highest-exposure thing this system does — the grid is what
    people judge an account by, where a Short is one impression in a feed. A
    scheduled post can be cancelled; a published one cannot.

Everything here fails safe: any failure leaves nothing scheduled rather than
publishing something unreviewed.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.carousel import build_carousel, judge_carousel
from src.caption_generator import generate_caption
from src.config import (
    CAROUSEL_MIN_SCORE,
    CAROUSEL_TARGET_HOUR,
    TIMEZONE,
)
from src.content_generator import generate_content
from src.media_host import publish_media
from src.postpeer import schedule_carousel


def _next_slot() -> datetime:
    """The next occurrence of the target hour, in the audience's timezone.

    Audience timezone, not the operator's — the account is written for a US
    audience and the operator is in Hawaii, so posting on local time would land
    everything in the small hours for almost everyone reading it.
    """
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    slot = now.replace(hour=CAROUSEL_TARGET_HOUR, minute=0, second=0, microsecond=0)
    if slot <= now + timedelta(minutes=20):
        slot += timedelta(days=1)
    return slot


def run(dry_run: bool = False) -> bool:
    content = generate_content(post_type="short")
    if not content:
        print("FAILED: could not generate a line")
        return False
    quote, theme = content["text"], content["theme"]
    print(f'Line:  "{quote}"')
    print(f"Theme: {theme}")

    car = build_carousel(quote, theme)
    if not car:
        return False

    caption = generate_caption(quote, theme)

    verdict = judge_carousel(car["paths"], quote, caption)
    print(f"  Judge: {verdict['score']}/10 coherent={verdict['coherent']} "
          f"lead={verdict['lead']} caption_ok={verdict['caption_ok']}")
    print(f"         {verdict['reason']}")

    if verdict["score"] < CAROUSEL_MIN_SCORE or not verdict["coherent"]:
        print(f"  Rejected by judge (need {CAROUSEL_MIN_SCORE}+ and coherent) — nothing scheduled")
        return False

    # One retry on a caption that does not connect. The images are the expensive
    # part and they are fine; only the words missed.
    if not verdict["caption_ok"]:
        print("  Caption missed — regenerating once")
        caption = generate_caption(quote, theme)

    # Lead with the slide the judge picked. Slide one is the grid thumbnail and
    # the only frame most people see, and it is often not the one that generated
    # first.
    paths = list(car["paths"])
    lead = verdict["lead"] - 1
    if 0 < lead < len(paths):
        paths.insert(0, paths.pop(lead))
        print(f"  Reordered to lead with slide {verdict['lead']}")

    print(f"\nCaption: {caption.splitlines()[0]}")
    for p in paths:
        print(f'  open "{p}"')

    if dry_run:
        print("\n(dry run — nothing uploaded or scheduled)")
        return True

    urls = [u for u in (publish_media(p) for p in paths) if u]
    if len(urls) < 3:
        print("FAILED: not enough slides reached a public URL")
        return False

    slot = _next_slot()
    print(f"\nScheduling for {slot:%Y-%m-%d %H:%M %Z}")
    post_id = schedule_carousel(urls, caption, slot.astimezone(timezone.utc))
    if not post_id:
        return False

    print(f"  Scheduled: {post_id}")
    print(f"  Cancel with: DELETE /v1/posts/scheduled/{post_id}")
    return True
