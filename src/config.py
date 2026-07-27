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

# LLM (via OpenRouter — supports DeepSeek, Claude, Gemini, Kimi, etc.)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# The writer. Deliberately NOT a frontier model, against expectation.
#
# Tested head to head on identical canon prompts: DeepSeek averaged 58 characters,
# Opus 5 averaged 94, Sonnet 5 averaged 115 and broke the two-sentence rule. The
# task is extreme compression, and the frontier is tuned toward elaboration —
# thoroughness is a liability inside 60 characters, so DeepSeek's bluntness is an
# asset rather than a saving. The prompt was the bottleneck all along, not the
# model: the same DeepSeek that wrote "Your comfort zone is stealing your wealth"
# writes "Laziness is a loan shark. The vig is paid in regret." given the canon.
# Sample was small (n=2-3 per model) — text_model is in the variant log so this
# gets settled by subs-per-1k rather than by taste.
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat-v3-0324")

# The judge. Scores candidates against explicit criteria — wants consistency, not
# brilliance, so it runs cheap and separate from the writer.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "anthropic/claude-haiku-4.5")

# Candidates generated per post. Best-of-N is the direct attack on cliche: an LLM
# given an underspecified creative brief returns the most probable phrasing, and
# for aphorisms the most probable phrasing IS the cliche. The best of six beats
# the mean of one by a wide margin, for roughly the same money.
CANDIDATES_PER_POST = int(os.getenv("CANDIDATES_PER_POST", "6"))

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

# ElevenLabs TTS — OFF as a decision, not a default.
#
# The image engine spends real effort on provenance: available light, film grain,
# gaze away from the lens, off-centre crops, all so a frame reads as found rather
# than generated. A synthetic voice announces "machine-made" in the first half
# second and cancels that work — the two pull against each other. Silence is the
# authentic option here, so video length stays at ~10s rather than being padded
# out to fit narration. Do not enable without revisiting that trade.
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
    "autonomy",
    "productivity",
    "leadership",
    "stoicism",
    "self_improvement",
]

# Image engine — generated photographic backgrounds behind the quote.
#
# Off by default: every enabled post publishes a generated image to a real
# channel with no human in the loop, so this stays opt-in until the model slug
# and the house style have been eyeballed via `run_youtube.py verify-image`.
IMAGE_ENGINE_ENABLED = os.getenv("IMAGE_ENGINE_ENABLED", "false").lower() == "true"
# Everything routes through OpenRouter — its Image API carries the same models,
# so the existing OPENROUTER_API_KEY covers text, images, and the vision gate.
# One key, one provider, no second SDK.
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "openrouter")
# Seedream 4.5 is the default for its film-like grade, which is the register we
# want. Swap freely — the model is a variable in the learning loop, not a
# constant, and every generated post records which model produced it.
# NOTE: OpenRouter's slug is `bytedance-seed/...`, not Replicate's `bytedance/...`.
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "bytedance-seed/seedream-4.5")
# Candidates generated per post. Best-of-N is how the vision gate earns its keep:
# score each, publish the best. Also the same mechanism carousels will need.
IMAGE_CANDIDATES = int(os.getenv("IMAGE_CANDIDATES", "2"))
# Multimodal model that reviews generated frames before they publish.
VISION_GATE_ENABLED = os.getenv("VISION_GATE_ENABLED", "true").lower() == "true"
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-3.1-flash-lite")
# Fraction of posts that get a generated background. 0.5 runs photo against the
# existing black cards 50/50 so subs-per-1k decides which wins, rather than us.
IMAGE_BACKGROUND_RATIO = float(os.getenv("IMAGE_BACKGROUND_RATIO", "0.5"))

# PostPeer — unified posting API. Used instead of the Graph API directly because
# they have already passed Meta's App Review, which would otherwise be weeks.
POSTPEER_ACCESS_KEY = os.getenv("POSTPEER_ACCESS_KEY", "")
# The PostPeer Integration._id, NOT the Instagram-native numeric id their
# dashboard displays. Discover via GET /v1/connect/integrations.
POSTPEER_IG_ACCOUNT_ID = os.getenv("POSTPEER_IG_ACCOUNT_ID", "")
# Reels per day. Deliberately below the 5/day Shorts cadence: Instagram's
# tolerance for volume from a new account is lower than YouTube's, and 5 Reels a
# day out of nowhere reads as spam. The variant log will tell us if this is wrong.
REELS_PER_DAY = int(os.getenv("REELS_PER_DAY", "2"))
# Whether a Reel also lands in the main grid. True keeps the grid populated;
# false reserves the grid for carousels, which is the Based-Living-style plan.
POSTPEER_SHARE_REELS_TO_FEED = os.getenv("POSTPEER_SHARE_REELS_TO_FEED", "false").lower() == "true"

# Carousels. Target hour is in TIMEZONE (the audience's, America/New_York) — the
# operator is in Hawaii, so scheduling on local time would land every post in the
# small hours for nearly everyone reading it. 11am ET is the weekday midday slot.
CAROUSEL_TARGET_HOUR = int(os.getenv("CAROUSEL_TARGET_HOUR", "11"))
# The whole-set judge must clear this before anything is scheduled. Higher than
# the per-slide gate's 4: a carousel is four images plus a line plus a caption
# going to the grid, which is the surface people judge an account by.
CAROUSEL_MIN_SCORE = int(os.getenv("CAROUSEL_MIN_SCORE", "6"))

# Display typeface, bundled in assets/fonts so CI and local render identically.
# Both shipped faces are slabs rather than high-contrast didones — editorial
# authority without borrowing the reference account's Playfair-style fingerprint.
#   ZillaSlab-Bold.ttf  humanist slab, a little warmth
#   Arvo-Bold.ttf       geometric slab, heavier and blunter
BRAND_FONT = os.getenv("BRAND_FONT", "ZillaSlab-Bold.ttf")

# Hook archetypes — the opening sentence structure.
#
# The first sentence is the strongest performance lever we actually control, so
# these are sampled by learned weight (data/hook_scores.json) rather than
# uniformly at random. Keys are STABLE IDENTIFIERS used for score attribution:
# renaming one discards its learning history, so add new archetypes instead of
# editing existing keys.
#
# `future_self` is split out from the generic `vivid_scenario` because the
# future-self frame appeared in 4 of the 8 best-converting videos as of
# 2026-07-26 — splitting it lets the loop confirm or refute that.
HOOK_STYLES = {
    "dollar_math": "a specific dollar amount or number that shocks (e.g. '$7 a day becomes $2.1 million')",
    "you_accusation": "a direct 'you' accusation that stings (e.g. 'You're subsidizing someone else's dream')",
    "counterintuitive": "a counterintuitive claim that sounds wrong but is true (e.g. 'Saving money is making you poor')",
    "comparison": "a comparison between two things (e.g. 'A gym membership costs $50. Diabetes costs $500,000')",
    "time_urgency": "a time-based urgency (e.g. 'Every hour you delay costs you $11 in lost compound growth')",
    "status_challenge": "a status/identity challenge (e.g. 'Rich people don't have savings accounts')",
    "future_self": "a confrontation with their future self watching them right now (e.g. 'Your future self is watching you scroll')",
    "vivid_scenario": "a vivid concrete scenario that is not about their future self (e.g. 'You are renting your life by the hour')",
}

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
