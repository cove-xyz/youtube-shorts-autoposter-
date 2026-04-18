import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
VIDEOS_DIR = DATA_DIR / "videos"
AUDIO_DIR = DATA_DIR / "audio"
DB_PATH = DATA_DIR / "instagram_poster.db"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# LLM (via OpenRouter — supports DeepSeek, Claude, Gemini, etc.)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat-v3-0324")

# Legacy / Instagram API keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
INSTAGRAM_BUSINESS_ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")

# Email
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")

# Timezone
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

# Image hosting (Instagram only — YouTube uses direct upload)
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# Instagram scheduling (24h format)
FEED_TIMES = ["07:00", "13:00", "19:00"]
STORY_TIMES = ["08:00", "11:00", "14:00", "17:00", "21:00"]

# YouTube
YOUTUBE_CHANNEL_NAME = os.getenv("YOUTUBE_CHANNEL_NAME", "MASTERING MONEY")
YOUTUBE_HANDLE = os.getenv("YOUTUBE_HANDLE", "@masteringmoneyxyz")
YOUTUBE_CLIENT_SECRET_PATH = DATA_DIR / "client_secret.json"
YOUTUBE_TOKEN_PATH = DATA_DIR / "youtube_token.json"
YOUTUBE_VIDEO_DURATION = int(os.getenv("YOUTUBE_VIDEO_DURATION", "10"))
YOUTUBE_CATEGORY_ID = os.getenv("YOUTUBE_CATEGORY_ID", "22")  # People & Blogs

# ElevenLabs TTS (set ELEVENLABS_ENABLED=true in .env to turn on)
ELEVENLABS_ENABLED = os.getenv("ELEVENLABS_ENABLED", "false").lower() == "true"
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# TikTok
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "https://masteringmoney.xyz/tiktok-callback")
TIKTOK_TOKEN_PATH = DATA_DIR / "tiktok_token.json"

# Content themes
CONTENT_THEMES = [
    "wealth_building",
    "mindset",
    "discipline",
    "investing",
    "entrepreneurship",
    "financial_freedom",
    "productivity",
    "leadership",
    "stoicism",
    "self_improvement",
]

# Safety filter keywords to avoid
BLOCKED_TOPICS = [
    "buy this stock",
    "guaranteed returns",
    "get rich quick",
    "financial advice",
    "not financial advice",
    "political",
    "violence",
    "sexual",
    "crypto pump",
    "insider",
]
