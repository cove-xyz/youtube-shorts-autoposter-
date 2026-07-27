"""Public URLs for generated media, via GitHub Release assets.

Every cross-posting route needs a publicly reachable URL: PostPeer's `mediaItems`
takes `{"url": ...}` and will not accept an upload, and Meta's Graph API has the
same requirement natively. Until now nothing retained the files at all —
`create_and_post_short()` deleted the MP4 immediately after the YouTube upload, so
there was nothing left to point at.

Release assets are used rather than committing files to the repo, because five
videos a day at ~0.5 MB would add roughly 75 MB a month to git history
permanently. Release assets live outside the object graph, can be pruned, and
serve from a stable public URL with a correct content type.

Auth comes from the `gh` CLI, which is preinstalled on GitHub runners and already
authenticated there via GITHUB_TOKEN. The workflow already grants `contents:
write`, which covers releases.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Assets are grouped into one release per day, so pruning is a whole-release
# delete rather than asset bookkeeping.
TAG_PREFIX = "media"
KEEP_DAYS = 14


def _run(args: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "gh CLI not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def _repo() -> str | None:
    """owner/repo for the current checkout, or None if it cannot be determined."""
    code, out = _run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], 60)
    return out.strip() if code == 0 and out.strip() else None


def _today_tag() -> str:
    return f"{TAG_PREFIX}-{datetime.now(timezone.utc):%Y-%m-%d}"


def publish_media(path: str | Path, tag: str | None = None) -> str | None:
    """Upload a file as a release asset and return its public URL.

    Returns None on any failure. Callers must treat that as "no cross-post this
    time" rather than an error — a hosting problem should never cost the YouTube
    upload that already succeeded.
    """
    path = Path(path)
    if not path.exists():
        print(f"  media_host: {path} does not exist")
        return None

    repo = _repo()
    if not repo:
        print("  media_host: could not determine repo (gh unavailable or unauthenticated)")
        return None

    tag = tag or _today_tag()

    # Create the day's release if it is not there yet. Failure is fine and
    # expected on every run after the first.
    _run([
        "gh", "release", "create", tag,
        "--title", f"Generated media {tag.removeprefix(TAG_PREFIX + '-')}",
        "--notes", "Auto-generated media assets for cross-posting. Safe to delete.",
    ], 90)

    code, out = _run(["gh", "release", "upload", tag, str(path), "--clobber"], 300)
    if code != 0:
        print(f"  media_host: upload failed — {out[:200]}")
        return None

    url = f"https://github.com/{repo}/releases/download/{tag}/{path.name}"
    print(f"  media_host: {url}")
    return url


def prune_old_releases(keep_days: int = KEEP_DAYS) -> int:
    """Delete media releases older than keep_days. Returns how many were removed."""
    code, out = _run(["gh", "release", "list", "--limit", "200", "--json", "tagName"], 90)
    if code != 0:
        return 0
    try:
        tags = [r["tagName"] for r in json.loads(out)]
    except (json.JSONDecodeError, KeyError, TypeError):
        return 0

    cutoff = datetime.now(timezone.utc).date()
    removed = 0
    for tag in tags:
        if not tag.startswith(TAG_PREFIX + "-"):
            continue
        try:
            day = datetime.strptime(tag.removeprefix(TAG_PREFIX + "-"), "%Y-%m-%d").date()
        except ValueError:
            continue
        if (cutoff - day).days > keep_days:
            c, _ = _run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], 90)
            removed += 1 if c == 0 else 0
    return removed


def verify() -> bool:
    """Round-trip check: upload a small file, fetch it back, confirm it matches."""
    import tempfile
    import urllib.request

    repo = _repo()
    print(f"repo        : {repo or 'UNKNOWN'}")
    if not repo:
        print("\nRun `gh auth status` — the CLI must be authenticated with repo write access.")
        return False

    payload = f"media-host round trip {datetime.now(timezone.utc).isoformat()}"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "_mediahost_check.txt"
        p.write_text(payload)
        url = publish_media(p, tag=f"{TAG_PREFIX}-selftest")
        if not url:
            return False
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                got = r.read().decode()
        except Exception as e:
            print(f"fetch failed: {type(e).__name__} — asset may still be propagating")
            return False

    ok = got.strip() == payload
    print(f"round trip  : {'PASS' if ok else 'MISMATCH'}")
    print(f"cleanup     : gh release delete {TAG_PREFIX}-selftest --yes --cleanup-tag")
    return ok
