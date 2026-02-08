import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "instagram_poster.db"

IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# API keys
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

# Image hosting
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

# Scheduling (24h format)
FEED_TIMES = ["07:00", "13:00", "19:00"]
STORY_TIMES = ["08:00", "11:00", "14:00", "17:00", "21:00"]

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
