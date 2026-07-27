"""Publishing to Instagram (and later others) through PostPeer.

PostPeer is a unified posting API that has already passed the platform app
reviews — Meta's App Review and TikTok's Content Posting audit — so we post
through their approved apps instead of spending weeks getting our own. That
tradeoff is why this module exists rather than a direct Graph API client.

Two things about the request shape that the quickstart docs get wrong, both
confirmed against the OpenAPI spec at https://api.postpeer.dev/docs/openapi.json:

  * `mediaItems` is TOP-LEVEL, not a property of the platform object. Nesting it
    inside `platforms[0]` returns "must NOT have additional properties", because
    each platform entry is a closed schema accepting only platform, accountId,
    content and platformSpecificData.
  * `accountId` is the PostPeer Integration._id (a 24-char hex ObjectId), not the
    Instagram-native numeric user id shown in their dashboard. Look it up via
    GET /v1/connect/integrations.
"""
import requests

from src.config import (
    POSTPEER_ACCESS_KEY,
    POSTPEER_IG_ACCOUNT_ID,
    POSTPEER_SHARE_REELS_TO_FEED,
)

API = "https://api.postpeer.dev/v1"


def _headers() -> dict:
    return {"x-access-key": POSTPEER_ACCESS_KEY, "Content-Type": "application/json"}


def list_integrations() -> list[dict]:
    """Connected accounts. The only way to discover a valid accountId."""
    if not POSTPEER_ACCESS_KEY:
        return []
    try:
        r = requests.get(f"{API}/connect/integrations", headers=_headers(), timeout=30)
        r.raise_for_status()
        return r.json().get("integrations", [])
    except Exception as e:
        print(f"  postpeer: could not list integrations ({type(e).__name__})")
        return []


def _post(payload: dict) -> dict | None:
    try:
        r = requests.post(f"{API}/posts/", json=payload, headers=_headers(), timeout=90)
    except requests.RequestException as e:
        print(f"  postpeer: request failed ({type(e).__name__})")
        return None

    if r.status_code >= 400:
        # Verbatim — schema complaints name the offending field
        print(f"  postpeer: HTTP {r.status_code} {r.text[:300]}")
        return None

    body = r.json()
    if not body.get("success"):
        print(f"  postpeer: rejected — {str(body.get('message'))[:200]}")
        return None

    for p in body.get("platforms", []):
        if not p.get("success"):
            print(f"  postpeer: {p.get('platform')} failed — {str(p.get('error'))[:160]}")
    return body


def publish_reel(video_url: str, caption: str, cover_url: str | None = None) -> str | None:
    """Publish a vertical video to Instagram as a Reel. Returns postId or None."""
    if not (POSTPEER_ACCESS_KEY and POSTPEER_IG_ACCOUNT_ID):
        print("  postpeer: not configured, skipping")
        return None

    ig: dict = {"shareToFeed": POSTPEER_SHARE_REELS_TO_FEED}
    if cover_url:
        # Our first video frame is type over a photo; letting Instagram pick a
        # cover often lands mid-fade on a half-drawn line.
        ig["coverUrl"] = cover_url

    body = _post({
        "content": caption,
        "publishNow": True,
        "mediaItems": [{"url": video_url, "type": "video"}],
        "platforms": [{
            "platform": "instagram",
            "accountId": POSTPEER_IG_ACCOUNT_ID,
            "platformSpecificData": ig,
        }],
    })
    if body:
        print(f"  Reel published: {body.get('postId')}")
        return body.get("postId")
    return None


def publish_carousel(image_urls: list[str], caption: str) -> str | None:
    """Publish an Instagram carousel. Returns postId or None.

    Instagram caps a carousel at 10 items; anything beyond that is dropped here
    rather than letting the platform reject the whole post.
    """
    if not (POSTPEER_ACCESS_KEY and POSTPEER_IG_ACCOUNT_ID):
        print("  postpeer: not configured, skipping")
        return None
    if not image_urls:
        return None

    if len(image_urls) > 10:
        print(f"  postpeer: trimming carousel from {len(image_urls)} to 10 (Instagram limit)")
        image_urls = image_urls[:10]

    body = _post({
        "content": caption,
        "publishNow": True,
        "mediaItems": [{"url": u, "type": "image"} for u in image_urls],
        "platforms": [{
            "platform": "instagram",
            "accountId": POSTPEER_IG_ACCOUNT_ID,
        }],
    })
    if body:
        print(f"  Carousel published ({len(image_urls)} slides): {body.get('postId')}")
        return body.get("postId")
    return None


def schedule_carousel(image_urls: list[str], caption: str, when) -> str | None:
    """Schedule a carousel for a future time. Returns postId or None.

    Scheduling rather than publishing immediately is deliberate — see
    carousel_publisher for why the gap doubles as the review window.
    """
    if not (POSTPEER_ACCESS_KEY and POSTPEER_IG_ACCOUNT_ID) or not image_urls:
        return None
    if len(image_urls) > 10:
        image_urls = image_urls[:10]

    body = _post({
        "content": caption,
        "scheduledFor": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timezone": "UTC",
        "mediaItems": [{"url": u, "type": "image"} for u in image_urls],
        "platforms": [{"platform": "instagram", "accountId": POSTPEER_IG_ACCOUNT_ID}],
    })
    return body.get("postId") if body else None


def cancel_scheduled(post_id: str) -> bool:
    """Cancel a scheduled post. Note: DELETE /v1/posts/{id} refuses while a post
    is still scheduled — it must be cancelled through this path first."""
    try:
        r = requests.delete(f"{API}/posts/scheduled/{post_id}", headers=_headers(), timeout=30)
        return r.status_code < 400 and r.json().get("success", False)
    except Exception as e:
        print(f"  postpeer: cancel failed ({type(e).__name__})")
        return False


def verify() -> bool:
    """Report configuration and connected accounts without posting anything."""
    print(f"access key : {'set' if POSTPEER_ACCESS_KEY else 'MISSING'}")
    print(f"ig account : {POSTPEER_IG_ACCOUNT_ID or 'MISSING'}")
    if not POSTPEER_ACCESS_KEY:
        print("\nSet POSTPEER_ACCESS_KEY in .env.")
        return False

    integrations = list_integrations()
    print(f"\nconnected accounts ({len(integrations)}):")
    matched = False
    for i in integrations:
        mark = "  <- configured" if i.get("id") == POSTPEER_IG_ACCOUNT_ID else ""
        matched = matched or bool(mark)
        print(f"  {i.get('platform'):10} {i.get('username'):24} id={i.get('id')}{mark}")

    if integrations and not matched:
        print("\nWARNING: POSTPEER_IG_ACCOUNT_ID matches none of the above.")
    return matched
