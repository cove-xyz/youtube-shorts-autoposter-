import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from src.config import (
    CONTENT_THEMES,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    NOTIFY_EMAIL,
)
from src.database import (
    get_posted_posts,
    update_engagement,
    update_theme_score,
    get_theme_scores,
)
from src.instagram_api import get_media_insights


def refresh_engagement(days: int = 7):
    """Pull latest engagement metrics for recent posts."""
    posts = get_posted_posts(days=days)
    print(f"[ENGAGEMENT] Refreshing metrics for {len(posts)} posts...")

    for post in posts:
        if not post.get("instagram_id"):
            continue
        try:
            metrics = get_media_insights(post["instagram_id"])
            update_engagement(post["id"], metrics)
        except Exception as e:
            print(f"[WARN] Failed to get metrics for post {post['id']}: {e}")


def recalculate_theme_scores():
    """Recalculate theme performance scores based on engagement data."""
    posts = get_posted_posts(days=30)

    theme_data: dict[str, list[float]] = {t: [] for t in CONTENT_THEMES}

    for post in posts:
        theme = post.get("theme", "")
        if theme not in theme_data:
            continue

        engagement = (
            post.get("likes", 0)
            + post.get("comments", 0) * 3  # comments weighted higher
            + post.get("saves", 0) * 2
            + post.get("shares", 0) * 4
        )
        reach = max(post.get("reach", 1), 1)
        engagement_rate = engagement / reach
        theme_data[theme].append(engagement_rate)

    # Calculate scores (normalized 0.5 - 2.0 range)
    all_rates = []
    for rates in theme_data.values():
        all_rates.extend(rates)

    if not all_rates:
        return

    global_avg = sum(all_rates) / len(all_rates) if all_rates else 1.0

    for theme, rates in theme_data.items():
        if not rates:
            score = 1.0
            avg_eng = 0.0
        else:
            avg_eng = sum(rates) / len(rates)
            score = max(0.5, min(2.0, avg_eng / global_avg if global_avg > 0 else 1.0))

        update_theme_score(theme, score, len(rates), avg_eng)

    print("[ENGAGEMENT] Theme scores recalculated")


def generate_weekly_report() -> str:
    """Generate a weekly summary report."""
    posts = get_posted_posts(days=7)
    scores = get_theme_scores()

    total_posts = len(posts)
    feed_posts = [p for p in posts if p["post_type"] == "feed"]
    story_posts = [p for p in posts if p["post_type"] == "story"]

    total_likes = sum(p.get("likes", 0) for p in posts)
    total_comments = sum(p.get("comments", 0) for p in posts)
    total_reach = sum(p.get("reach", 0) for p in posts)
    total_saves = sum(p.get("saves", 0) for p in posts)
    total_shares = sum(p.get("shares", 0) for p in posts)

    # Best performing post
    best_post = None
    best_engagement = 0
    for p in feed_posts:
        eng = p.get("likes", 0) + p.get("comments", 0) * 3 + p.get("saves", 0) * 2
        if eng > best_engagement:
            best_engagement = eng
            best_post = p

    # Top themes
    sorted_themes = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    report = f"""
MASTERING MONEY - Weekly Report
{datetime.now().strftime('%B %d, %Y')}
{'=' * 50}

POSTING SUMMARY
  Feed posts:  {len(feed_posts)}
  Stories:     {len(story_posts)}
  Total:       {total_posts}

ENGAGEMENT
  Likes:       {total_likes:,}
  Comments:    {total_comments:,}
  Saves:       {total_saves:,}
  Shares:      {total_shares:,}
  Total Reach: {total_reach:,}

TOP THEMES (by engagement score)
"""
    for theme, score in sorted_themes[:5]:
        report += f"  {theme:25s} {score:.2f}x\n"

    if best_post:
        report += f"""
BEST PERFORMING POST
  "{best_post.get('content_text', 'N/A')[:80]}..."
  Likes: {best_post.get('likes', 0)} | Comments: {best_post.get('comments', 0)} | Saves: {best_post.get('saves', 0)}
"""

    report += f"\n{'=' * 50}\n"
    return report


def send_weekly_email():
    """Send the weekly report via email."""
    if not all([SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL]):
        print("[WARN] Email not configured, skipping weekly email")
        return

    report = generate_weekly_report()

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = f"MASTERING MONEY Weekly Report - {datetime.now().strftime('%B %d')}"
    msg.attach(MIMEText(report, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print("[OK] Weekly report email sent")
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
