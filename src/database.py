import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager
from src.config import DB_PATH


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_text TEXT NOT NULL,
                caption TEXT,
                image_path TEXT,
                post_type TEXT NOT NULL CHECK(post_type IN ('feed', 'story')),
                theme TEXT,
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN ('queued', 'approved', 'posted', 'failed', 'rejected')),
                instagram_id TEXT,
                posted_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                reach INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                saves INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS content_hashes (
                hash TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS engagement_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER REFERENCES posts(id),
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                reach INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                saves INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS theme_scores (
                theme TEXT PRIMARY KEY,
                score REAL DEFAULT 1.0,
                total_posts INTEGER DEFAULT 0,
                avg_engagement REAL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def content_exists(content_hash: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM content_hashes WHERE hash = ?", (content_hash,)
        ).fetchone()
        return row is not None


def save_content_hash(content_hash: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO content_hashes (hash) VALUES (?)", (content_hash,)
        )


def queue_post(
    content_text: str,
    caption: str,
    image_path: str,
    post_type: str,
    theme: str,
    status: str = "approved",
) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO posts (content_text, caption, image_path, post_type, theme, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (content_text, caption, image_path, post_type, theme, status),
        )
        return cursor.lastrowid


def get_next_post(post_type: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM posts
               WHERE status = 'approved' AND post_type = ?
               ORDER BY created_at ASC LIMIT 1""",
            (post_type,),
        ).fetchone()
        return dict(row) if row else None


def mark_posted(post_id: int, instagram_id: str):
    with get_db() as conn:
        conn.execute(
            """UPDATE posts SET status = 'posted', instagram_id = ?, posted_at = ?
               WHERE id = ?""",
            (instagram_id, datetime.now().isoformat(), post_id),
        )


def mark_failed(post_id: int):
    with get_db() as conn:
        conn.execute("UPDATE posts SET status = 'failed' WHERE id = ?", (post_id,))


def update_engagement(post_id: int, metrics: dict):
    with get_db() as conn:
        conn.execute(
            """UPDATE posts SET likes=?, comments=?, reach=?, impressions=?, saves=?, shares=?
               WHERE id = ?""",
            (
                metrics.get("likes", 0),
                metrics.get("comments", 0),
                metrics.get("reach", 0),
                metrics.get("impressions", 0),
                metrics.get("saves", 0),
                metrics.get("shares", 0),
                post_id,
            ),
        )
        conn.execute(
            """INSERT INTO engagement_log (post_id, likes, comments, reach, impressions, saves, shares)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                post_id,
                metrics.get("likes", 0),
                metrics.get("comments", 0),
                metrics.get("reach", 0),
                metrics.get("impressions", 0),
                metrics.get("saves", 0),
                metrics.get("shares", 0),
            ),
        )


def get_posted_posts(days: int = 7) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM posts WHERE status = 'posted' AND posted_at >= ?
               ORDER BY posted_at DESC""",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_theme_scores() -> dict[str, float]:
    with get_db() as conn:
        rows = conn.execute("SELECT theme, score FROM theme_scores").fetchall()
        return {r["theme"]: r["score"] for r in rows}


def update_theme_score(theme: str, score: float, total_posts: int, avg_engagement: float):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO theme_scores (theme, score, total_posts, avg_engagement, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(theme) DO UPDATE SET
                   score=excluded.score,
                   total_posts=excluded.total_posts,
                   avg_engagement=excluded.avg_engagement,
                   updated_at=excluded.updated_at""",
            (theme, score, total_posts, avg_engagement, datetime.now().isoformat()),
        )


def get_queue_count(post_type: str) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM posts WHERE status = 'approved' AND post_type = ?",
            (post_type,),
        ).fetchone()
        return row["cnt"]


def get_all_queued() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status IN ('queued', 'approved') ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]
