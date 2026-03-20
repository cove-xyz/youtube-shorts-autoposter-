#!/usr/bin/env python3
"""YouTube Shorts Auto-Poster - MASTERING MONEY

Usage:
    python run_youtube.py post        Generate and upload one Short
    python run_youtube.py preview     Generate one Short without uploading
    python run_youtube.py batch N     Generate and upload N Shorts (max 5)
    python run_youtube.py verify      Test YouTube API credentials
    python run_youtube.py queue       Show database queue status

Designed to be run by Perplexity Computer or manually.
Each invocation is self-contained — no daemon, no scheduler.
"""
import sys
import time

from src.database import init_db, get_queue_count, get_all_queued


def cmd_post():
    from src.youtube_poster import create_and_post_short
    result = create_and_post_short()
    if result:
        print(f"\nSUCCESS: {result['url']}")
        sys.exit(0)
    else:
        print("\nFAILED: Could not create or upload Short")
        sys.exit(1)


def cmd_preview():
    from src.youtube_poster import preview_short
    result = preview_short()
    if not result:
        print("\nFAILED: Could not generate preview")
        sys.exit(1)


def cmd_batch():
    from src.youtube_poster import create_and_post_short

    count = 2
    if len(sys.argv) >= 3:
        try:
            count = min(int(sys.argv[2]), 5)  # Cap at 5 (quota safety)
        except ValueError:
            pass

    print(f"Posting {count} Shorts...\n")
    results = []
    for i in range(count):
        print(f"=== Short {i + 1}/{count} ===")
        result = create_and_post_short()
        if result:
            results.append(result)
        if i < count - 1:
            print("\nWaiting 60s before next upload...\n")
            time.sleep(60)

    print(f"\n=== Results: {len(results)}/{count} uploaded ===")
    for r in results:
        print(f"  {r['url']}")

    sys.exit(0 if results else 1)


def cmd_verify():
    from src.youtube_api import verify_credentials
    success = verify_credentials()
    sys.exit(0 if success else 1)


def cmd_queue():
    init_db()
    short_count = get_queue_count("short")
    feed_count = get_queue_count("feed")
    story_count = get_queue_count("story")
    print(f"YouTube Shorts queue: {short_count}")
    print(f"Instagram Feed queue: {feed_count}")
    print(f"Instagram Story queue: {story_count}")
    print()
    items = get_all_queued()
    for item in items:
        print(f"  [{item['post_type']:5s}] [{item['status']:8s}] {item['content_text'][:70]}...")


COMMANDS = {
    "post": cmd_post,
    "preview": cmd_preview,
    "batch": cmd_batch,
    "verify": cmd_verify,
    "queue": cmd_queue,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
