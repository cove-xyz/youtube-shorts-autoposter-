import os
from pathlib import Path

from src.config import YOUTUBE_CHANNEL_NAME, ELEVENLABS_ENABLED
from src.content_generator import generate_content
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

    # 1. Generate content
    print("[1/7] Generating content...")
    content = generate_content(post_type="short")
    if not content:
        print("  FAILED: Could not generate content")
        return None

    quote = content["text"]
    theme = content["theme"]
    print(f'  Quote: "{quote}"')
    print(f"  Theme: {theme}")

    # 2. Safety check
    print("[2/7] Safety check...")
    safe, reason = is_safe(quote)
    if not safe:
        print(f"  REJECTED: {reason}")
        return None
    print("  Passed")

    # 3. Generate image (1080x1920) — used as thumbnail
    print("[3/7] Generating image...")
    image_path = generate_youtube_image(quote)
    print(f"  Image: {image_path}")

    # 4. Generate voiceover
    print("[4/7] Generating voiceover...")
    voice_path = _generate_voice(quote)

    # 5. Create video (text reveal + voice + music)
    print("[5/7] Creating video...")
    video_path = create_video(quote, voice_path=voice_path)

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

    # Save to DB
    post_id = queue_post(
        content_text=quote,
        caption=description,
        image_path=str(image_path),
        post_type="short",
        theme=theme,
        status="posted",
    )
    mark_posted(post_id, result["id"])

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

    print("[4/6] Generating voiceover...")
    voice_path = _generate_voice(quote)

    print("[5/6] Creating video...")
    video_path = create_video(quote, voice_path=voice_path)

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
