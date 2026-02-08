import time
import requests
from src.config import META_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _headers():
    return {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}


def publish_feed_post(image_url: str, caption: str) -> str | None:
    """Publish a feed post via Meta Graph API.

    Steps:
    1. Create a media container with the image URL and caption
    2. Publish the container

    Returns the Instagram media ID or None on failure.
    """
    # Step 1: Create media container
    resp = requests.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media",
        params={
            "image_url": image_url,
            "caption": caption,
            "access_token": META_ACCESS_TOKEN,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"[ERROR] Media container creation failed: {resp.text}")
        return None

    container_id = resp.json().get("id")
    if not container_id:
        print(f"[ERROR] No container ID returned: {resp.text}")
        return None

    # Wait for container to be ready
    time.sleep(5)

    # Step 2: Publish the container
    resp = requests.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": META_ACCESS_TOKEN,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"[ERROR] Publish failed: {resp.text}")
        return None

    media_id = resp.json().get("id")
    print(f"[OK] Feed post published: {media_id}")
    return media_id


def publish_story(image_url: str) -> str | None:
    """Publish a story via Meta Graph API."""
    # Step 1: Create story container
    resp = requests.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media",
        params={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": META_ACCESS_TOKEN,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"[ERROR] Story container creation failed: {resp.text}")
        return None

    container_id = resp.json().get("id")
    if not container_id:
        return None

    time.sleep(5)

    # Step 2: Publish
    resp = requests.post(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": META_ACCESS_TOKEN,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"[ERROR] Story publish failed: {resp.text}")
        return None

    media_id = resp.json().get("id")
    print(f"[OK] Story published: {media_id}")
    return media_id


def get_media_insights(media_id: str) -> dict:
    """Fetch engagement metrics for a media post."""
    metrics = "likes,comments,shares,saved,reach,impressions"
    resp = requests.get(
        f"{GRAPH_API_BASE}/{media_id}/insights",
        params={
            "metric": metrics,
            "access_token": META_ACCESS_TOKEN,
        },
        timeout=15,
    )

    result = {
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "saves": 0,
        "reach": 0,
        "impressions": 0,
    }

    if resp.status_code != 200:
        # Fallback: try basic fields
        resp2 = requests.get(
            f"{GRAPH_API_BASE}/{media_id}",
            params={
                "fields": "like_count,comments_count",
                "access_token": META_ACCESS_TOKEN,
            },
            timeout=15,
        )
        if resp2.status_code == 200:
            data = resp2.json()
            result["likes"] = data.get("like_count", 0)
            result["comments"] = data.get("comments_count", 0)
        return result

    data = resp.json().get("data", [])
    for metric in data:
        name = metric.get("name", "")
        value = metric.get("values", [{}])[0].get("value", 0)
        if name == "saved":
            result["saves"] = value
        elif name in result:
            result[name] = value

    return result


def verify_credentials() -> bool:
    """Verify that Instagram API credentials are working."""
    resp = requests.get(
        f"{GRAPH_API_BASE}/{INSTAGRAM_BUSINESS_ACCOUNT_ID}",
        params={
            "fields": "username,name,followers_count,media_count",
            "access_token": META_ACCESS_TOKEN,
        },
        timeout=15,
    )

    if resp.status_code == 200:
        data = resp.json()
        print(f"[OK] Connected to @{data.get('username', 'unknown')}")
        print(f"     Followers: {data.get('followers_count', 0)}")
        print(f"     Posts: {data.get('media_count', 0)}")
        return True

    print(f"[ERROR] Credential verification failed: {resp.text}")
    return False
