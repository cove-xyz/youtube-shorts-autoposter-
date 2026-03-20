# YouTube Shorts Pipeline — Implementation Plan

## Context

The existing Instagram auto-poster generates AI quotes (via Claude), renders them as images (via Pillow), and posts them to Instagram on a schedule. We're adding a **YouTube Shorts pipeline** alongside it, designed so **Perplexity Computer can operate the entire system end-to-end**.

## Architectural Constraints

- **Perplexity Computer is the operator.** It has a Linux sandbox with Python, ffmpeg, and HTTP access — but the sandbox resets between sessions. No persistent filesystem.
- **Codebase is the source of truth.** The repo (cloned from GitHub each session) contains all logic. Credentials are stored as environment variables or a single token file that Perplexity Computer re-creates from its memory.
- **Minimal infrastructure.** No servers, no Docker, no Heroku needed for YouTube Shorts. Unlike Instagram (which requires a Flask server to host images for Meta's API), YouTube accepts direct file uploads.
- **Default YouTube API quota allows 6 uploads/day.** We only need 1-2/day.

## What Changes

### New Files

| File | Purpose |
|------|---------|
| `src/video_generator.py` | Convert 1080x1920 PNG → 30s MP4 via ffmpeg subprocess |
| `src/youtube_api.py` | YouTube Data API v3 client: OAuth2 auth + video upload + metadata |
| `src/youtube_poster.py` | Orchestrator: generate content → image → video → upload |
| `run_youtube.py` | Single-command entry point for Perplexity Computer |

### Modified Files

| File | Change |
|------|--------|
| `src/config.py` | Add YouTube-specific config (channel ID, default tags, category) |
| `src/database.py` | Add `platform` column to posts table (`instagram` or `youtube`) |
| `src/content_generator.py` | No changes — reuse as-is |
| `src/image_generator.py` | Minor tweak: expose story-size generation as `generate_youtube_image()` |
| `src/caption_generator.py` | Add `generate_youtube_description()` — longer format, no hashtags, SEO-friendly |
| `src/safety_filter.py` | No changes — reuse as-is |
| `requirements.txt` | Add `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` |

### No Changes Needed

- `src/instagram_api.py` — untouched, Instagram pipeline stays independent
- `src/engagement_tracker.py` — phase 2 (YouTube analytics can come later)
- `src/scheduler.py` — not needed; Perplexity Computer runs on-demand, not as a daemon
- `src/image_server.py` — not needed; YouTube accepts direct file uploads
- `Dockerfile`, `Procfile` — not needed for YouTube pipeline

## Implementation Steps

### Step 1: Video Generator (`src/video_generator.py`)
Create a module that converts a static PNG image into a valid YouTube Shorts MP4.

- Use `ffmpeg` via `subprocess.run()`
- Input: 1080x1920 PNG image path
- Output: MP4 file (H.264, yuv420p, 24fps, 30 seconds, AAC audio if music provided)
- Add a subtle slow-zoom (Ken Burns) effect via ffmpeg filter to avoid a frozen-frame feel
- FFmpeg command:
  ```
  ffmpeg -y -loop 1 -i {image} -c:v libx264 -t 30 -pix_fmt yuv420p
    -vf "scale=1080:1920,zoompan=z='min(zoom+0.0005,1.1)':d=720:s=1080x1920"
    -r 24 -tune stillimage -movflags +faststart {output}
  ```
- Verify ffmpeg is available, raise clear error if not
- Return output path

### Step 2: YouTube API Client (`src/youtube_api.py`)
Handle OAuth2 authentication and video uploads.

- **Auth flow:**
  - Look for `data/youtube_token.json` (cached credentials)
  - If missing or expired, use `data/client_secret.json` to run OAuth consent flow
  - Store refresh token in `data/youtube_token.json`
  - Auto-refresh access tokens via google-auth library
- **Upload function:**
  - `upload_short(video_path, title, description, tags, category_id="22")`
  - Use `MediaFileUpload` with `resumable=True`
  - Set `privacyStatus` to "public"
  - Set `selfDeclaredMadeForKids` to False
  - Include `#Shorts` in title
  - Return video ID and URL on success
- **Verify function:**
  - `verify_credentials()` — test auth, print channel name and subscriber count

### Step 3: YouTube Poster (`src/youtube_poster.py`)
Orchestrate the full pipeline.

- `create_and_post_short()`:
  1. Generate content via `content_generator.generate_content()`
  2. Run through `safety_filter.is_safe()`
  3. Generate image via `image_generator.generate_story_image()` (1080x1920)
  4. Convert to video via `video_generator.create_video()`
  5. Generate YouTube description via `caption_generator.generate_youtube_description()`
  6. Upload via `youtube_api.upload_short()`
  7. Save to database with `platform='youtube'`
  8. Clean up temp video file
  9. Return result dict with video ID and URL
- `create_short_preview()`:
  - Same as above but skip upload step
  - Return content + image path + description for review

### Step 4: Caption Generator Update (`src/caption_generator.py`)
Add YouTube-specific description generation.

- `generate_youtube_description(content_text, theme)`:
  - Claude prompt: write a 2-3 sentence YouTube description expanding on the quote
  - Append standard channel boilerplate (subscribe CTA, relevant keywords)
  - No hashtags in description body (YouTube uses tags separately)
  - Return description string
- `generate_youtube_tags(theme)`:
  - Return list of 8-10 tags relevant to theme + channel
  - Include "Shorts", "motivation", theme-specific tags

### Step 5: Config Update (`src/config.py`)
Add YouTube configuration.

- `YOUTUBE_CHANNEL_NAME` — for branding
- `YOUTUBE_DEFAULT_TAGS` — base tags for all uploads
- `YOUTUBE_CATEGORY_ID` — default "22" (People & Blogs)
- `YOUTUBE_VIDEO_DURATION` — default 30 seconds
- `YOUTUBE_CLIENT_SECRET_PATH` — path to OAuth client secret file
- `YOUTUBE_TOKEN_PATH` — path to cached token

### Step 6: Database Update (`src/database.py`)
Add platform awareness.

- Add `platform TEXT DEFAULT 'instagram'` column to posts table
- Update `queue_post()` to accept platform parameter
- Update `get_next_post()` to filter by platform
- Migration: ALTER TABLE for existing data

### Step 7: Single-Command Entry Point (`run_youtube.py`)
The script Perplexity Computer runs.

```python
"""
YouTube Shorts auto-poster.
Usage: python run_youtube.py [post|preview|verify]
"""
```

- `python run_youtube.py post` — generate and upload one Short
- `python run_youtube.py preview` — generate content, show without uploading
- `python run_youtube.py verify` — test YouTube API credentials
- `python run_youtube.py batch N` — generate and upload N Shorts (with 60s delay between)
- On startup: init database, validate config, check ffmpeg availability
- Print clear status messages at each pipeline stage
- Exit with code 0 on success, 1 on failure

### Step 8: Update requirements.txt
Add:
```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
google-auth-httplib2>=0.2.0
```

## Perplexity Computer Operating Procedure

When Perplexity Computer runs this system, the session looks like:

```
1. Clone repo:        git clone <repo-url> && cd instagram-auto-poster
2. Install deps:      pip install -r requirements.txt
3. Set credentials:   Write .env file from memory, write client_secret.json from memory
4. Verify auth:       python run_youtube.py verify
5. Post a Short:      python run_youtube.py post
6. (Optional):        python run_youtube.py batch 2
```

That's it. 6 commands, fully autonomous.

## What Perplexity Computer Handles vs What Stays in Code

| Responsibility | Owner | Why |
|---------------|-------|-----|
| Clone repo + install deps | Perplexity Computer | Sandbox resets each session |
| Write `.env` and `client_secret.json` | Perplexity Computer | Credentials stored in its memory, written fresh each session |
| Run `python run_youtube.py post` | Perplexity Computer | Triggers the pipeline |
| Content generation (Claude API) | Codebase | Deterministic, in `content_generator.py` |
| Image rendering | Codebase | Deterministic, in `image_generator.py` |
| Video conversion (ffmpeg) | Codebase | ffmpeg pre-installed on Perplexity Computer |
| YouTube upload (API) | Codebase | OAuth handled in `youtube_api.py` |
| Safety filtering | Codebase | Rules in code, not runtime decisions |
| Choosing when/how often to post | Perplexity Computer | Can be scheduled via its own task system |
| Monitoring upload success/failure | Codebase (exit codes + stdout) | Perplexity Computer reads output |
| YouTube analytics | Phase 2 | Not in initial build |
| OAuth token refresh | Codebase (google-auth handles automatically) | Transparent to operator |

## What We're NOT Building (Phase 2+)

- YouTube engagement tracking / analytics
- YouTube-specific theme scoring
- Background music / audio overlay
- Advanced video animations (text fade-in, transitions)
- Multi-platform posting in a single run
- Webhook-based scheduling
- Dashboard / web UI

## File Tree After Implementation

```
instagram-auto-poster/
├── main.py                      # Instagram CLI (unchanged)
├── run_youtube.py               # YouTube Shorts CLI (NEW)
├── requirements.txt             # Updated with google-api deps
├── .env.example                 # Updated with YouTube vars
├── src/
│   ├── config.py                # Updated: YouTube config added
│   ├── database.py              # Updated: platform column
│   ├── content_generator.py     # Unchanged — shared
│   ├── caption_generator.py     # Updated: YouTube description/tags
│   ├── image_generator.py       # Minor update: expose for YouTube
│   ├── safety_filter.py         # Unchanged — shared
│   ├── video_generator.py       # NEW: PNG → MP4 via ffmpeg
│   ├── youtube_api.py           # NEW: OAuth2 + upload
│   ├── youtube_poster.py        # NEW: pipeline orchestrator
│   ├── instagram_api.py         # Unchanged
│   ├── poster.py                # Unchanged
│   ├── scheduler.py             # Unchanged
│   ├── engagement_tracker.py    # Unchanged
│   └── image_server.py          # Unchanged
├── data/
│   ├── instagram_poster.db      # SQLite (shared, extended)
│   ├── images/                  # Generated images
│   ├── videos/                  # Generated videos (NEW)
│   ├── client_secret.json       # YouTube OAuth (gitignored)
│   └── youtube_token.json       # Cached OAuth token (gitignored)
└── tests/
```

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| OAuth token expires (7-day limit in Testing mode) | Set Google Cloud project to Production mode; document this in setup |
| ffmpeg not available | `video_generator.py` checks on import, raises clear error |
| YouTube API quota exceeded | Default 1 upload/day; `batch` command caps at 5 |
| Content fails safety filter | Retry up to 3 times with new generation |
| Duplicate content | SHA-256 hash check (existing system) |
| Perplexity Computer sandbox resets | All state reconstructable from repo + credentials in memory |
| YouTube rejects upload | Clear error messages with YouTube's error codes parsed |
