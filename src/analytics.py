"""YouTube Analytics: fetch per-video stats and update theme scores for learning loop.

Works in two modes:
1. Full sync: pulls ALL video stats from YouTube, infers themes from descriptions,
   computes performance scores, exports to theme_scores.json
2. DB sync: also updates the local posts table for videos posted through the pipeline

This means the learning loop uses ALL channel videos, not just pipeline-tracked ones.
"""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from googleapiclient.discovery import build

from src.youtube_api import _get_credentials
from src.database import get_db, init_db, update_theme_score
from src.config import CONTENT_THEMES, DATA_DIR


# Map description hashtags back to themes
HASHTAG_TO_THEME = {
    "#wealth": "wealth_building",
    "#buildwealth": "wealth_building",
    "#financialgrowth": "wealth_building",
    "#mindset": "mindset",
    "#growthmindset": "mindset",
    "#winnermindset": "mindset",
    "#discipline": "discipline",
    "#grind": "discipline",
    "#noexcuses": "discipline",
    "#investing": "investing",
    "#finance": "investing",
    "#smartmoney": "investing",
    "#entrepreneur": "entrepreneurship",
    "#business": "entrepreneurship",
    "#hustle": "entrepreneurship",
    "#financialfreedom": "financial_freedom",
    "#passiveincome": "financial_freedom",
    "#productivity": "productivity",
    "#focus": "productivity",
    "#leadership": "leadership",
    "#stoicism": "stoicism",
    "#selfimprovement": "self_improvement",
    "#growth": "self_improvement",
}


def _get_analytics_service():
    creds = _get_credentials()
    return build("youtubeAnalytics", "v2", credentials=creds)


def _get_data_service():
    creds = _get_credentials()
    return build("youtube", "v3", credentials=creds)


def _infer_theme(description: str) -> str | None:
    """Infer theme from hashtags in description."""
    lower = description.lower()
    theme_votes: dict[str, int] = {}
    for tag, theme in HASHTAG_TO_THEME.items():
        if tag in lower:
            theme_votes[theme] = theme_votes.get(theme, 0) + 1
    if theme_votes:
        return max(theme_votes, key=theme_votes.get)
    return None


def _fetch_video_metadata(data_svc, video_ids: list[str]) -> dict[str, dict]:
    """Fetch title + description for a batch of video IDs."""
    metadata = {}
    # YouTube API allows max 50 IDs per request
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = data_svc.videos().list(
            part="snippet",
            id=",".join(batch),
        ).execute()
        for item in resp.get("items", []):
            vid = item["id"]
            metadata[vid] = {
                "title": item["snippet"]["title"],
                "description": item["snippet"].get("description", ""),
            }
    return metadata


def fetch_video_stats(days: int = 30) -> list[dict]:
    """Fetch view/watch-time stats for all videos in the last N days.

    Returns list of dicts with video_id, views, watch_time_minutes, avg_view_pct.
    """
    analytics = _get_analytics_service()
    data_svc = _get_data_service()

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
            metrics="views,estimatedMinutesWatched,averageViewPercentage,likes,subscribersGained",
            dimensions="video",
            sort="-views",
            maxResults=200,
        ).execute()
    except Exception as e:
        print(f"ERROR fetching analytics: {e}")
        return []

    rows = resp.get("rows", [])
    if not rows:
        return []

    # Fetch metadata for all videos so we can infer themes
    video_ids = [row[0] for row in rows]
    metadata = _fetch_video_metadata(data_svc, video_ids)

    results = []
    for row in rows:
        vid = row[0]
        meta = metadata.get(vid, {})
        theme = _infer_theme(meta.get("description", ""))

        results.append({
            "video_id": vid,
            "views": int(row[1]),
            "watch_time_minutes": float(row[2]),
            "avg_view_pct": float(row[3]),
            "likes": int(row[4]),
            "subscribers_gained": int(row[5]),
            "title": meta.get("title", ""),
            "theme": theme,
        })

    return results


def sync_to_db(stats: list[dict]):
    """Update the local posts table with view counts for tracked videos."""
    init_db()
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
    return updated


# Scoring weights. Subscriber conversion leads because it is the actual goal —
# the previous 70/30 views/watch-time split optimized for reach the channel was
# already getting, which is how views recovered while subs stayed flat. Views
# stay in the mix so a theme that converts well but cannot get distribution
# does not crowd out everything else.
W_SUBS = 0.60    # subscribers gained per 1k views
W_VIEWS = 0.25   # avg views per video
W_WATCH = 0.15   # avg watch-through %

# Smoothing prior, in thousands of views. A theme with 200 views and 1 sub would
# otherwise read as 5.0 subs/1k and dominate the weighting on noise alone. This
# pulls thin themes toward the channel-wide rate until they earn real volume.
SUBS_PRIOR_KVIEWS = 2.0


def compute_theme_scores(stats: list[dict]) -> dict[str, dict]:
    """Compute theme scores directly from YouTube stats (not the DB).

    Composite signal: 60% subscriber conversion + 25% avg views + 15% watch-through.
    Returns dict of theme -> {score, count, avg_views, avg_watch_pct, subs_per_1k}.
    """
    # Group stats by theme
    by_theme: dict[str, list[dict]] = {}
    for s in stats:
        theme = s.get("theme")
        if theme:
            by_theme.setdefault(theme, []).append(s)

    if not by_theme:
        return {}

    # Channel-wide conversion rate, used as the smoothing prior
    total_views = sum(s["views"] for s in stats) or 1
    total_subs = sum(s.get("subscribers_gained", 0) for s in stats)
    channel_subs_per_1k = (total_subs / total_views) * 1000

    # Compute per-theme aggregates
    theme_data = {}
    for theme, videos in by_theme.items():
        avg_views = sum(v["views"] for v in videos) / len(videos)
        avg_watch_pct = sum(v["avg_view_pct"] for v in videos) / len(videos)
        theme_views = sum(v["views"] for v in videos)
        theme_subs = sum(v.get("subscribers_gained", 0) for v in videos)

        # Smoothed subs per 1k views, shrunk toward the channel rate
        kviews = theme_views / 1000
        subs_per_1k = (
            (theme_subs + SUBS_PRIOR_KVIEWS * channel_subs_per_1k)
            / (kviews + SUBS_PRIOR_KVIEWS)
        )

        theme_data[theme] = {
            "count": len(videos),
            "avg_views": avg_views,
            "avg_watch_pct": avg_watch_pct,
            "total_views": theme_views,
            "total_subs": theme_subs,
            "subs_per_1k": subs_per_1k,
        }

    # Normalize to 0.5–2.0 range using composite signal
    max_views = max(d["avg_views"] for d in theme_data.values()) or 1
    max_watch = max(d["avg_watch_pct"] for d in theme_data.values()) or 1
    max_subs = max(d["subs_per_1k"] for d in theme_data.values()) or 1

    for theme, d in theme_data.items():
        subs_norm = d["subs_per_1k"] / max_subs       # 0–1
        view_norm = d["avg_views"] / max_views        # 0–1
        watch_norm = d["avg_watch_pct"] / max_watch   # 0–1
        composite = (W_SUBS * subs_norm) + (W_VIEWS * view_norm) + (W_WATCH * watch_norm)
        score = round(0.5 + (composite * 1.5), 3)    # 0.5–2.0
        d["score"] = score
        update_theme_score(theme, score, d["count"], round(d["avg_views"], 1))

    # Untested themes keep neutral score
    for theme in CONTENT_THEMES:
        if theme not in theme_data:
            update_theme_score(theme, 1.0, 0, 0.0)
            theme_data[theme] = {
                "count": 0, "avg_views": 0, "avg_watch_pct": 0,
                "total_views": 0, "total_subs": 0, "subs_per_1k": 0.0, "score": 1.0,
            }

    return theme_data


def export_theme_scores_json(theme_data: dict[str, dict]):
    """Export theme scores to data/theme_scores.json for GitHub Actions."""
    scores = {theme: d["score"] for theme, d in theme_data.items()}
    out_path = DATA_DIR / "theme_scores.json"
    out_path.write_text(json.dumps(scores, indent=2))
    print(f"\n  Exported to {out_path}")


def print_report(stats: list[dict], theme_data: dict[str, dict]):
    """Print human-readable analytics report."""
    themed = [s for s in stats if s.get("theme")]
    unthemed = [s for s in stats if not s.get("theme")]

    print(f"\n=== YOUTUBE SHORTS ANALYTICS ({len(stats)} videos) ===")
    if unthemed:
        print(f"  ({len(unthemed)} videos couldn't be matched to a theme)")

    print(f"\n{'Views':>7}  {'Watch%':>6}  {'Likes':>5}  {'Subs':>4}  {'Theme':<20}  {'Title'}")
    print("-" * 96)
    for s in stats[:20]:
        title = s["title"][:40] + "..." if len(s["title"]) > 40 else s["title"]
        theme = s.get("theme") or "?"
        print(
            f"{s['views']:>7}  {s['avg_view_pct']:>5.1f}%  {s['likes']:>5}  "
            f"{s.get('subscribers_gained', 0):>4}  {theme:<20}  {title}"
        )

    total_views = sum(s["views"] for s in stats) or 1
    total_subs = sum(s.get("subscribers_gained", 0) for s in stats)
    print(f"\n  Channel conversion: {total_subs} subs / {total_views} views "
          f"= {(total_subs / total_views) * 1000:.2f} per 1k views")

    print(f"\n=== THEME SCORES (learning loop) ===")
    print(f"{'Score':>6}  {'Videos':>6}  {'Avg Views':>9}  {'Watch%':>7}  {'Subs':>5}  {'Subs/1k':>8}  {'Theme'}")
    print("-" * 78)
    sorted_themes = sorted(theme_data.items(), key=lambda x: x[1]["score"], reverse=True)
    for theme, d in sorted_themes:
        print(
            f"{d['score']:>6.2f}  {d['count']:>6}  {d['avg_views']:>9.0f}  "
            f"{d['avg_watch_pct']:>6.1f}%  {d.get('total_subs', 0):>5}  "
            f"{d.get('subs_per_1k', 0):>8.2f}  {theme}"
        )

    print("\n(Score 0.5–2.0 | higher = content generator picks this theme more often)")
    print(f"(Signal: {int(W_SUBS * 100)}% subs-per-1k-views + {int(W_VIEWS * 100)}% avg views "
          f"+ {int(W_WATCH * 100)}% watch-through)")
    print(f"(Subs/1k is smoothed toward the channel rate with a {SUBS_PRIOR_KVIEWS}k-view prior)")


def run_analytics_sync(days: int = 30):
    """Full analytics pipeline: fetch stats → compute scores → export → report."""
    init_db()

    print(f"Fetching YouTube Analytics (last {days} days)...")
    stats = fetch_video_stats(days=days)

    if not stats:
        print("  No data returned.")
        return

    print(f"  Found {len(stats)} videos")

    # Sync view counts to local DB for tracked videos
    db_updated = sync_to_db(stats)
    print(f"  Updated {db_updated} pipeline-tracked videos in DB")

    # Compute scores from ALL videos (not just DB-tracked ones)
    theme_data = compute_theme_scores(stats)
    export_theme_scores_json(theme_data)
    print_report(stats, theme_data)
