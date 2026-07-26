import os
import random
from pathlib import Path

from src.config import (
    YOUTUBE_CHANNEL_NAME,
    ELEVENLABS_ENABLED,
    YOUTUBE_VIDEO_DURATION,
    IMAGE_ENGINE_ENABLED,
    IMAGE_BACKGROUND_RATIO,
)
from src.content_generator import generate_content, _save_posted_title
from src.image_engine import generate_background
from src.variants import record_variant
from src.caption_generator import generate_youtube_description, generate_youtube_tags
from src.image_generator import generate_youtube_image
from src.safety_filter import is_safe, filter_caption
from src.video_generator import create_video
from src.youtube_api import upload_short
from src.database import init_db, queue_post, mark_posted, mark_failed


def _generate_voice(quote: str) -> Path | None:
    """Generate voiceover if ElevenLabs is enabled. Returns path or None."""
    if not ELEVENLABS_ENABLED:
        print("  Skipping (disabled — set ELEVENLABS_ENABLED=true in .env)")
        return None
    try:
        from src.voice import generate_voiceover
        path = generate_voiceover(quote)
        print(f"  Voice: {path.name}")
        return path
    except Exception as e:
        print(f"  Voice generation failed: {e}")
        return None


def create_and_post_short() -> dict | None:
    """Full pipeline: generate content -> voice -> video -> upload to YouTube.

    Returns dict with video details on success, None on failure.
    """
    init_db()

    # 1. Generate content (with retry on safety failure)
    content = None
    for attempt in range(3):
        print(f"[1/7] Generating content (attempt {attempt + 1}/3)...")
        content = generate_content(post_type="short")
        if not content:
            print("  FAILED: Could not generate content")
            continue

        quote = content["text"]
        theme = content["theme"]
        print(f'  Quote: "{quote}"')
        print(f"  Theme: {theme}")

        # 2. Safety check
        print("[2/7] Safety check...")
        safe, reason = is_safe(quote)
        if safe:
            print("  Passed")
            break
        else:
            print(f"  REJECTED: {reason} — retrying...")
            content = None

    if not content:
        print("  FAILED: Could not generate safe content after 3 attempts")
        return None

    # 3. Generate image (1080x1920) — used as thumbnail
    print("[3/7] Generating image...")
    image_path = generate_youtube_image(quote)
    print(f"  Image: {image_path}")

    # 3b. Generated photographic background, on a coin flip.
    # Split rather than switched: the plain cards are the control arm, so
    # subs-per-1k decides whether photography actually converts better instead
    # of us assuming it does. Both arms are recorded in the variant log.
    background = None
    if IMAGE_ENGINE_ENABLED and random.random() < IMAGE_BACKGROUND_RATIO:
        print("  Generating photographic background...")
        background = generate_background(quote, theme)
    background_path = background["path"] if background else None

    # 4. Generate voiceover
    print("[4/7] Generating voiceover...")
    voice_path = _generate_voice(quote)

    # 5. Create video (text reveal + voice + music)
    print("[5/7] Creating video...")
    video_path = create_video(quote, voice_path=voice_path, background_path=background_path)

    # 6. Generate title + description + tags
    print("[6/7] Generating metadata...")
    title = _make_title(quote)
    description = generate_youtube_description(quote, theme)
    tags = generate_youtube_tags(theme)

    safe, reason = filter_caption(description)
    if not safe:
        print(f"  Description rejected: {reason}")
        return None

    print(f"  Title: {title}")

    # 7. Upload
    print("[7/7] Uploading to YouTube...")
    try:
        result = upload_short(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
        )
    except Exception as e:
        print(f"  UPLOAD FAILED: {e}")
        post_id = queue_post(
            content_text=quote,
            caption=description,
            image_path=str(image_path),
            post_type="short",
            theme=theme,
            status="failed",
        )
        return None

    # Save to DB + title history for dedup
    post_id = queue_post(
        content_text=quote,
        caption=description,
        image_path=str(image_path),
        post_type="short",
        theme=theme,
        status="posted",
    )
    mark_posted(post_id, result["id"])
    # Record the full quote, not the truncated display title. `title` is cut at
    # 65 chars, which drops the payoff sentence and leaves the dedup check
    # comparing hooks only.
    _save_posted_title(quote)

    # Log every generation choice against the video_id so analytics can attribute
    # performance back to them. duration/voice are constants today, but recording
    # them now means they become learnable the moment they start varying.
    record_variant(
        result["id"],
        theme=theme,
        hook_style=content.get("hook_style"),
        duration_s=YOUTUBE_VIDEO_DURATION,
        voice=ELEVENLABS_ENABLED,
        source=content.get("source"),
        quote=quote,
        # `background` is the arm of the split this post landed in — "generated"
        # vs "plain" is the comparison the loop will score.
        background="generated" if background else "plain",
        image_model=background["model"] if background else None,
        image_subject=background["subject"] if background else None,
        # Recorded so we can later check whether the gate's score predicts
        # anything — a gate that does not correlate with performance is theatre.
        vision_score=background.get("vision_score") if background else None,
    )

    # Clean up video file (images are cheap, videos are large)
    try:
        os.remove(video_path)
    except OSError:
        pass

    print(f"\nDone: {result['url']}")
    return {
        "video_id": result["id"],
        "url": result["url"],
        "quote": quote,
        "theme": theme,
        "title": title,
    }


def preview_short() -> dict | None:
    """Generate content + voice + video without uploading. For review."""
    init_db()

    print("[1/6] Generating content...")
    content = generate_content(post_type="short")
    if not content:
        print("  FAILED: Could not generate content")
        return None

    quote = content["text"]
    theme = content["theme"]
    print(f'  Quote: "{quote}"')
    print(f"  Theme: {theme}")

    print("[2/6] Safety check...")
    safe, reason = is_safe(quote)
    if not safe:
        print(f"  REJECTED: {reason}")
        return None
    print("  Passed")

    print("[3/6] Generating image...")
    image_path = generate_youtube_image(quote)
    print(f"  Image: {image_path}")

    # Preview always attempts a background when the engine is on, ignoring the
    # split ratio — the point of a preview is to look at the thing being tested.
    background = None
    if IMAGE_ENGINE_ENABLED:
        print("  Generating photographic background...")
        background = generate_background(quote, theme)
    background_path = background["path"] if background else None

    print("[4/6] Generating voiceover...")
    voice_path = _generate_voice(quote)

    print("[5/6] Creating video...")
    video_path = create_video(quote, voice_path=voice_path, background_path=background_path)

    print("[6/6] Generating metadata...")
    title = _make_title(quote)
    description = generate_youtube_description(quote, theme)
    tags = generate_youtube_tags(theme)

    print(f"\n--- PREVIEW ---")
    print(f"Title: {title}")
    print(f"Description:\n{description}")
    print(f"Tags: {', '.join(tags)}")
    print(f"Video: {video_path}")
    print(f"Open with: open \"{video_path}\"")

    return {
        "quote": quote,
        "theme": theme,
        "title": title,
        "description": description,
        "tags": tags,
        "image_path": str(image_path),
        "video_path": str(video_path),
    }


def _make_title(quote: str) -> str:
    """Create a YouTube title from a quote.

    Short, punchy, with the channel name. YouTube titles that create
    curiosity or tension get higher CTR.
    """
    # Truncate quote for title — keep it under 70 chars before #Shorts
    if len(quote) <= 65:
        return quote
    # Cut at last word boundary before 65 chars
    truncated = quote[:65].rsplit(" ", 1)[0]
    return f"{truncated}..."
