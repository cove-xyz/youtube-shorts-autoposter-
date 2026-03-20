import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.config import YOUTUBE_CLIENT_SECRET_PATH, YOUTUBE_TOKEN_PATH

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]


def _get_credentials() -> Credentials:
    """Load or create OAuth2 credentials.

    First run requires browser-based consent. After that, the refresh token
    is cached in youtube_token.json and reused automatically.
    """
    creds = None
    token_path = Path(YOUTUBE_TOKEN_PATH)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret_path = Path(YOUTUBE_CLIENT_SECRET_PATH)
            if not secret_path.exists():
                raise FileNotFoundError(
                    f"YouTube client secret not found at {secret_path}\n"
                    "Download it from Google Cloud Console > APIs & Services > Credentials\n"
                    "and save as data/client_secret.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
            print("\n=== YouTube Authorization ===")
            print("A browser window will open. Sign in and approve access.")
            print("If it doesn't open, check the URL printed below.\n")
            creds = flow.run_local_server(
                port=8090,
                authorization_prompt_message="Opening browser for auth... URL: {url}",
                success_message="Authorization complete! You can close this tab.",
                open_browser=True,
            )

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    return creds


def _get_service():
    creds = _get_credentials()
    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: str | Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_id: str = "22",
) -> dict:
    """Upload a video as a YouTube Short.

    Returns dict with 'id' and 'url' on success.
    """
    service = _get_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags or ["Shorts", "motivation", "money"],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Uploading: {pct}%")

    video_id = response["id"]
    url = f"https://youtube.com/shorts/{video_id}"
    print(f"  Uploaded: {url}")
    return {"id": video_id, "url": url}


def verify_credentials() -> bool:
    """Test YouTube API credentials and print channel info."""
    try:
        service = _get_service()
        resp = service.channels().list(part="snippet,statistics", mine=True).execute()

        if not resp.get("items"):
            print("ERROR: No YouTube channel found for this account.")
            return False

        channel = resp["items"][0]
        name = channel["snippet"]["title"]
        subs = channel["statistics"].get("subscriberCount", "hidden")
        videos = channel["statistics"].get("videoCount", "0")

        print(f"Channel: {name}")
        print(f"Subscribers: {subs}")
        print(f"Videos: {videos}")
        print("YouTube API credentials verified.")
        return True

    except Exception as e:
        print(f"ERROR: YouTube API verification failed: {e}")
        return False
