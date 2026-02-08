"""Scheduler that runs the posting pipeline on a cron-like schedule."""
import os
import time
from datetime import datetime
import schedule
from src.config import FEED_TIMES, STORY_TIMES, TIMEZONE
from src.database import init_db
from src.poster import post_next_feed, post_next_story, ensure_queue
from src.engagement_tracker import refresh_engagement, recalculate_theme_scores, send_weekly_email

# Set timezone
os.environ["TZ"] = TIMEZONE
try:
    time.tzset()
except AttributeError:
    pass  # Windows doesn't have tzset


def run_feed_post():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Running feed post...")
    try:
        post_next_feed()
    except Exception as e:
        print(f"[ERROR] Feed post failed: {e}")


def run_story_post():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Running story post...")
    try:
        post_next_story()
    except Exception as e:
        print(f"[ERROR] Story post failed: {e}")


def run_queue_refill():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Refilling content queue...")
    try:
        ensure_queue()
    except Exception as e:
        print(f"[ERROR] Queue refill failed: {e}")


def run_engagement_refresh():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Refreshing engagement data...")
    try:
        refresh_engagement()
        recalculate_theme_scores()
    except Exception as e:
        print(f"[ERROR] Engagement refresh failed: {e}")


def run_weekly_report():
    print(f"\n[{datetime.now().strftime('%H:%M')}] Generating weekly report...")
    try:
        refresh_engagement(days=7)
        recalculate_theme_scores()
        send_weekly_email()
    except Exception as e:
        print(f"[ERROR] Weekly report failed: {e}")


def start_scheduler():
    """Set up and run the scheduler."""
    init_db()

    # Schedule feed posts
    for t in FEED_TIMES:
        schedule.every().day.at(t).do(run_feed_post)
        print(f"[SCHED] Feed post at {t}")

    # Schedule story posts
    for t in STORY_TIMES:
        schedule.every().day.at(t).do(run_story_post)
        print(f"[SCHED] Story post at {t}")

    # Queue refill every 6 hours
    schedule.every(6).hours.do(run_queue_refill)
    print("[SCHED] Queue refill every 6 hours")

    # Engagement refresh every 4 hours
    schedule.every(4).hours.do(run_engagement_refresh)
    print("[SCHED] Engagement refresh every 4 hours")

    # Weekly report on Sundays at 10am
    schedule.every().sunday.at("10:00").do(run_weekly_report)
    print("[SCHED] Weekly report Sundays at 10:00")

    # Initial queue fill
    print("\n[INIT] Filling initial content queue...")
    ensure_queue()

    print(f"\n[RUNNING] Scheduler started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("[RUNNING] Press Ctrl+C to stop\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    start_scheduler()
