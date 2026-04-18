#!/usr/bin/env python3
"""YouTube Shorts + TikTok Auto-Poster - MASTERING MONEY

Usage:
    python run_youtube.py post           Generate and upload one Short (YouTube + TikTok)
    python run_youtube.py preview        Generate one Short without uploading
    python run_youtube.py batch N        Generate and upload N Shorts (max 5)
    python run_youtube.py verify         Test YouTube API credentials
    python run_youtube.py queue          Show database queue status
    python run_youtube.py analytics      Fetch YouTube Analytics, update theme scores
    python run_youtube.py analytics 7    Same but only last 7 days
    python run_youtube.py tiktok-auth    Start TikTok OAuth flow
    python run_youtube.py tiktok-verify  Test TikTok API credentials

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


def cmd_analytics():
    from src.analytics import run_analytics_sync
    init_db()
    days = 30
    if len(sys.argv) >= 3:
        try:
            days = int(sys.argv[2])
        except ValueError:
            pass
    run_analytics_sync(days=days)


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


def cmd_tiktok_auth():
    from src.tiktok_api import get_auth_url, exchange_code
    print("TikTok OAuth Authorization")
    print("=" * 40)
    url = get_auth_url()
    print(f"\n1. Open this URL in your browser:\n\n{url}\n")
    print("2. Authorize the app, then paste the FULL redirect URL here:")
    redirect_url = input("\nRedirect URL: ").strip()

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)

    if "code" not in params:
        print("ERROR: No authorization code found in URL")
        sys.exit(1)

    code = params["code"][0]
    print(f"\nExchanging code for token...")
    token = exchange_code(code)
    print("TikTok authorization complete!")


def cmd_tiktok_verify():
    from src.tiktok_api import verify_credentials
    print("Testing TikTok API credentials...")
    success = verify_credentials()
    sys.exit(0 if success else 1)


COMMANDS = {
    "post": cmd_post,
    "preview": cmd_preview,
    "batch": cmd_batch,
    "verify": cmd_verify,
    "queue": cmd_queue,
    "analytics": cmd_analytics,
    "tiktok-auth": cmd_tiktok_auth,
    "tiktok-verify": cmd_tiktok_verify,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)

    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
