"""TikTok Content Posting API: OAuth2 + direct video upload."""
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from src.config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_REDIRECT_URI,
    TIKTOK_TOKEN_PATH,
)

TOKEN_PATH = TIKTOK_TOKEN_PATH

API_BASE = "https://open.tiktokapis.com/v2"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"


def _save_token(token_data: dict):
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2))


def _load_token() -> dict | None:
    if TOKEN_PATH.exists():
        return json.loads(TOKEN_PATH.read_text())
    return None


def get_auth_url(state: str = "masteringmoney") -> str:
    """Generate the TikTok OAuth authorization URL."""
    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": "video.publish,video.upload",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    resp = requests.post(
        f"{API_BASE}/oauth/token/",
        data={
            "client_key": TIKTOK_CLIENT_KEY,
            "client_secret": TIKTOK_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": TIKTOK_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    data = resp.json()
    if "access_token" in data:
        _save_token(data)
        print(f"  TikTok token saved (expires in {data.get('expires_in', '?')}s)")
    else:
        raise RuntimeError(f"TikTok token exchange failed: {data}")
    return data


def _refresh_token() -> dict:
    """Refresh the access token using the refresh token."""
    token = _load_token()
    if not token or "refresh_token" not in token:
        raise RuntimeError("No TikTok refresh token. Re-authorize.")

    resp = requests.post(
        f"{API_BASE}/oauth/token/",
        data={
            "client_key": TIKTOK_CLIENT_KEY,
            "client_secret": TIKTOK_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    data = resp.json()
    if "access_token" in data:
        _save_token(data)
        return data
    raise RuntimeError(f"TikTok token refresh failed: {data}")


def _get_access_token() -> str:
    """Get a valid access token, refreshing if needed."""
    token = _load_token()
    if not token:
        raise RuntimeError(
            "No TikTok token found. Run: python run_youtube.py tiktok-auth"
        )
    # Access tokens last 24h — refresh proactively if we don't know expiry
    # For now, try the stored token first; refresh on 401
    return token["access_token"]


def _api_call(endpoint: str, body: dict = None, retry_on_401: bool = True) -> dict:
    """Make an authenticated API call, refreshing token on 401."""
    token = _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    resp = requests.post(f"{API_BASE}{endpoint}", json=body or {}, headers=headers)
    data = resp.json()

    # Check for token expiry
    error_code = data.get("error", {}).get("code", "")
    if error_code == "access_token_invalid" and retry_on_401:
        _refresh_token()
        return _api_call(endpoint, body, retry_on_401=False)

    return data


def query_creator_info() -> dict:
    """Query creator info to get available privacy levels."""
    data = _api_call("/post/publish/creator_info/query/")
    if data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"Creator info query failed: {data}")
    return data["data"]


def upload_video(
    video_path: str | Path,
    title: str = "",
    privacy_level: str = "SELF_ONLY",
) -> dict:
    """Upload a video to TikTok via Content Posting API.

    Returns dict with publish_id and status.
    """
    video_path = Path(video_path)
    video_size = video_path.stat().st_size

    # For small files (<64MB), single chunk upload
    chunk_size = video_size
    total_chunks = 1

    # Step 1: Query creator info for valid privacy levels
    print("  Querying creator info...")
    creator = query_creator_info()
    available_privacy = creator.get("privacy_level_options", [])
    if privacy_level not in available_privacy:
        # Fall back to most restrictive available option
        privacy_level = "SELF_ONLY" if "SELF_ONLY" in available_privacy else available_privacy[0]
        print(f"  Using privacy: {privacy_level}")

    # Step 2: Initialize upload
    print("  Initializing upload...")
    init_body = {
        "post_info": {
            "title": title[:2200],
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_stitch": False,
            "disable_comment": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        },
    }
    init_data = _api_call("/post/publish/video/init/", init_body)

    if init_data.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"Upload init failed: {init_data}")

    publish_id = init_data["data"]["publish_id"]
    upload_url = init_data["data"]["upload_url"]
    print(f"  Publish ID: {publish_id}")

    # Step 3: Upload video file
    print(f"  Uploading {video_size / 1024 / 1024:.1f} MB...")
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    resp = requests.put(
        upload_url,
        data=video_bytes,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(video_size),
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
    )
    print(f"  Upload response: {resp.status_code}")

    # Step 4: Poll for status
    print("  Polling publish status...")
    for i in range(30):
        time.sleep(3)
        status_data = _api_call(
            "/post/publish/status/fetch/",
            {"publish_id": publish_id},
        )
        status = status_data.get("data", {}).get("status", "UNKNOWN")
        print(f"  Status: {status}")

        if status == "PUBLISH_COMPLETE":
            post_ids = status_data["data"].get("publicaly_available_post_id", [])
            print(f"  Published! Post ID: {post_ids}")
            return {
                "publish_id": publish_id,
                "status": status,
                "post_ids": post_ids,
            }
        elif status == "FAILED":
            reason = status_data["data"].get("fail_reason", "unknown")
            raise RuntimeError(f"TikTok publish failed: {reason}")
        elif status in ("PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD"):
            continue
        elif status == "SEND_TO_USER_INBOX":
            print("  Sent to TikTok inbox (draft)")
            return {"publish_id": publish_id, "status": status}

    raise RuntimeError("TikTok publish timed out after 90 seconds")


def verify_credentials() -> bool:
    """Test TikTok API credentials."""
    try:
        creator = query_creator_info()
        print(f"  TikTok user: {creator.get('creator_nickname', '?')}")
        print(f"  Username: @{creator.get('creator_username', '?')}")
        print(f"  Privacy options: {creator.get('privacy_level_options', [])}")
        print(f"  Max video duration: {creator.get('max_video_post_duration_sec', '?')}s")
        return True
    except Exception as e:
        print(f"  TikTok verification failed: {e}")
        return False
