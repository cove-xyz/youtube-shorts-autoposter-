"""YouTube Analytics: fetch per-video stats and update theme scores for learning loop."""
import os
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from datetime import datetime, timedelta
from googleapiclient.discovery import build

from src.youtube_api import _get_credentials
from src.database import get_db, update_theme_score, get_theme_scores
from src.config import CONTENT_THEMES


def _get_analytics_service():
    creds = _get_credentials()
    return build("youtubeAnalytics", "v2", credentials=creds)


def _get_data_service():
    creds = _get_credentials()
    return build("youtube", "v3", credentials=creds)


def fetch_video_stats(days: int = 30) -> list[dict]:
    """Fetch view/watch-time stats for all posted Shorts in the last N days.

    Returns list of dicts with video_id, views, watch_time_minutes, avg_view_pct.
    """
    analytics = _get_analytics_service()
    data_svc = _get_data_service()

    # Get channel ID
    ch = data_svc.channels().list(part="id", mine=True).execute()
    if not ch.get("items"):
        print("ERROR: No channel found")
        return []
    channel_id = ch["items"][0]["id"]

    end_date = datetime.today().strftime("%Y-%m-%d")
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        resp = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewPercentage",
            dimensions="video",
            sort="-views",
            maxResults=50,
        ).execute()
    except Exception as e:
        print(f"ERROR fetching analytics: {e}")
        return []

    rows = resp.get("rows", [])
    results = []
    for row in rows:
        results.append({
            "video_id": row[0],
            "views": int(row[1]),
            "watch_time_minutes": float(row[2]),
            "avg_view_pct": float(row[3]),
        })
    return results


def sync_analytics_to_db(days: int = 30):
    """Pull YouTube stats and write them back to the posts table."""
    print(f"Fetching YouTube Analytics (last {days} days)...")
    stats = fetch_video_stats(days=days)

    if not stats:
        print("  No data returned.")
        return

    updated = 0
    with get_db() as conn:
        for s in stats:
            result = conn.execute(
                "SELECT id FROM posts WHERE platform_id = ?", (s["video_id"],)
            ).fetchone()
            if result:
                conn.execute(
                    "UPDATE posts SET views = ? WHERE id = ?",
                    (s["views"], result["id"]),
                )
                updated += 1

    print(f"  Updated {updated}/{len(stats)} videos in database.")
    return stats


def compute_theme_scores():
    """Recalculate theme scores based on average views per theme.

    Uses a weighted score: avg_views normalized relative to other themes,
    with a floor so under-tested themes still get picked occasionally.
    """
    with get_db() as conn:
        rows = conn.execute(
            """SELECT theme, COUNT(*) as cnt, AVG(views) as avg_views
               FROM posts
               WHERE status = 'posted' AND post_type = 'short' AND theme IS NOT NULL
               GROUP BY theme"""
        ).fetchall()

    if not rows:
        print("  No posted Shorts in database yet.")
        return

    data = [{"theme": r["theme"], "cnt": r["cnt"], "avg_views": r["avg_views"] or 0} for r in rows]
    max_views = max(d["avg_views"] for d in data) or 1

    for d in data:
        # Score: normalized 0.5–2.0 range so low performers still get picked
        normalized = d["avg_views"] / max_views  # 0.0–1.0
        score = 0.5 + (normalized * 1.5)         # 0.5–2.0
        update_theme_score(d["theme"], round(score, 3), d["cnt"], round(d["avg_views"], 1))

    # Themes with no posts yet keep default score of 1.0 (neutral)
    existing = {d["theme"] for d in data}
    for theme in CONTENT_THEMES:
        if theme not in existing:
            update_theme_score(theme, 1.0, 0, 0.0)

    return data


def print_analytics_report():
    """Print a human-readable analytics summary by theme."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.theme, p.content_text, p.views, p.platform_id, p.posted_at
               FROM posts p
               WHERE p.status = 'posted' AND p.post_type = 'short'
               ORDER BY p.views DESC"""
        ).fetchall()

        theme_rows = conn.execute(
            """SELECT theme, score, total_posts, avg_engagement
               FROM theme_scores
               ORDER BY score DESC"""
        ).fetchall()

    if not rows:
        print("No posted Shorts in database yet.")
        return

    print("\n=== TOP PERFORMING SHORTS ===")
    print(f"{'Views':>7}  {'Theme':<20}  {'Quote'}")
    print("-" * 80)
    for r in rows[:15]:
        quote = r["content_text"][:55] + "..." if len(r["content_text"]) > 55 else r["content_text"]
        url = f"https://youtube.com/shorts/{r['platform_id']}" if r["platform_id"] else ""
        print(f"{r['views']:>7}  {(r['theme'] or 'unknown'):<20}  {quote}")

    print("\n=== THEME PERFORMANCE SCORES ===")
    print(f"{'Score':>6}  {'Posts':>5}  {'Avg Views':>9}  {'Theme'}")
    print("-" * 50)
    for r in theme_rows:
        print(f"{r['score']:>6.2f}  {r['total_posts']:>5}  {r['avg_engagement'] or 0.0:>9.0f}  {r['theme']}")

    print("\n(Scores range 0.5–2.0. Higher = picked more often by content generator)")


def export_theme_scores_json():
    """Export theme scores to data/theme_scores.json for use by GitHub Actions."""
    from src.config import DATA_DIR
    import json

    with get_db() as conn:
        rows = conn.execute(
            "SELECT theme, score, total_posts, avg_engagement FROM theme_scores"
        ).fetchall()

    if not rows:
        return

    scores = {r["theme"]: r["score"] for r in rows}
    out_path = DATA_DIR.parent / "data" / "theme_scores.json"
    out_path.write_text(json.dumps(scores, indent=2))
    print(f"\n  Theme scores exported to {out_path}")
    print("  Commit this file to keep GitHub Actions in sync.")


def run_analytics_sync(days: int = 30):
    """Full analytics pipeline: fetch → sync DB → compute scores → print report."""
    sync_analytics_to_db(days=days)
    compute_theme_scores()
    print_analytics_report()
    export_theme_scores_json()
