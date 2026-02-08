#!/usr/bin/env python3
"""Instagram Auto-Poster - MASTERING MONEY

Usage:
    python main.py run          Start the scheduler (main loop)
    python main.py server       Start the image server
    python main.py generate     Generate content without posting
    python main.py post-feed    Post one feed item now
    python main.py post-story   Post one story now
    python main.py queue        Show queue status
    python main.py fill-queue   Fill up the content queue
    python main.py report       Generate and print weekly report
    python main.py verify       Verify Instagram API credentials
    python main.py preview      Generate one post and show it (no posting)
"""
import sys
from src.database import init_db, get_all_queued, get_queue_count


def cmd_run():
    from src.scheduler import start_scheduler
    start_scheduler()


def cmd_server():
    from src.image_server import app
    app.run(host="0.0.0.0", port=5000)


def cmd_generate():
    init_db()
    from src.poster import create_feed_content, create_story_content
    print("Generating feed post...")
    result = create_feed_content()
    if result:
        print(f"  Text: {result['text']}")
        print(f"  Image: {result['image']}")
    else:
        print("  Failed to generate feed content")

    print("\nGenerating story...")
    result = create_story_content()
    if result:
        print(f"  Text: {result['text']}")
        print(f"  Image: {result['image']}")
    else:
        print("  Failed to generate story content")


def cmd_post_feed():
    init_db()
    from src.poster import post_next_feed
    post_next_feed()


def cmd_post_story():
    init_db()
    from src.poster import post_next_story
    post_next_story()


def cmd_queue():
    init_db()
    feed_count = get_queue_count("feed")
    story_count = get_queue_count("story")
    print(f"Feed queue:  {feed_count}")
    print(f"Story queue: {story_count}")
    print()

    items = get_all_queued()
    for item in items:
        print(f"  [{item['post_type']:5s}] [{item['status']:8s}] {item['content_text'][:70]}...")


def cmd_fill_queue():
    init_db()
    from src.poster import ensure_queue
    ensure_queue()


def cmd_report():
    init_db()
    from src.engagement_tracker import generate_weekly_report
    print(generate_weekly_report())


def cmd_verify():
    from src.instagram_api import verify_credentials
    verify_credentials()


def cmd_preview():
    init_db()
    from src.content_generator import generate_content
    from src.image_generator import generate_feed_image
    from src.caption_generator import generate_caption
    from src.safety_filter import is_safe

    print("Generating preview...\n")
    content = generate_content()
    if not content:
        print("Failed to generate content")
        return

    safe, reason = is_safe(content["text"])
    print(f"Quote: \"{content['text']}\"")
    print(f"Theme: {content['theme']}")
    print(f"Safe: {safe} ({reason})")

    if safe:
        image_path = generate_feed_image(content["text"])
        caption = generate_caption(content["text"], content["theme"])
        print(f"\nCaption:\n{caption}")
        print(f"\nImage saved: {image_path}")
        print(f"Open with: open \"{image_path}\"")


COMMANDS = {
    "run": cmd_run,
    "server": cmd_server,
    "generate": cmd_generate,
    "post-feed": cmd_post_feed,
    "post-story": cmd_post_story,
    "queue": cmd_queue,
    "fill-queue": cmd_fill_queue,
    "report": cmd_report,
    "verify": cmd_verify,
    "preview": cmd_preview,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
