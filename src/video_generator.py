"""YouTube Shorts video generator.

Renders frames in Python (Pillow) with sentence-by-sentence text reveal,
then pipes raw frames to ffmpeg for encoding with voice + music.

The visual style:
- 1080x1920 pure black background
- Sentence 1 (hook) in GOLD — stops the scroll
- Sentence 2 in white, fades in at ~4s
- Large bold font (up to 72pt) for maximum screen presence
- Subtle progress bar at top
- CTA "FOLLOW @masteringmoneyxyz" subtle from start, bright in last 2s
- AI voiceover (ElevenLabs) mixed with background music
"""

import random
import re
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.config import (
    VIDEOS_DIR,
    AUDIO_DIR,
    BASE_DIR,
    BRAND_FONT,
    YOUTUBE_CHANNEL_NAME,
    YOUTUBE_VIDEO_DURATION,
    YOUTUBE_HANDLE,
)

WIDTH, HEIGHT = 1080, 1920
FPS = 24

# All type is white. The previous gold hook was the single most recognisable
# signal of a motivational-quote page — the exact register our own theme scores
# rank worst. Both sentences are the same weight and colour now; the
# sentence-by-sentence reveal already does the emphasis work that colour was doing.
TEXT_COLOR = (255, 255, 255)

# --- Font loading ---

# Repo-bundled display face, first in the list on every platform.
#
# Before this, the candidate list started with macOS system fonts and fell
# through to Liberation/DejaVu — meaning local renders were Futura Condensed
# ExtraBold while every video actually published from the Ubuntu runner was a
# generic Helvetica clone, or PIL's default bitmap if neither was installed. The
# brand had no consistent typeface at all. Bundling the file makes rendering
# identical everywhere and turns the typeface into a decision instead of an
# accident. Swap with BRAND_FONT (see config) — both bundled faces are slabs
# rather than high-contrast didones, deliberately unlike the reference account's
# Playfair-style treatment, which is its fingerprint and not ours to take.
_BUNDLED_FONT = BASE_DIR / "assets" / "fonts" / BRAND_FONT

FONT_CANDIDATES_BOLD = [
    (str(_BUNDLED_FONT), 0),
    # Fallbacks only — if these are ever reached, the bundled file is missing
    ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 0),
]

FONT_CANDIDATES_LIGHT = [
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 0),   # Futura Medium
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
]


def _find_font(size: int, candidates=None) -> ImageFont.FreeTypeFont:
    if candidates is None:
        candidates = FONT_CANDIDATES_BOLD
    for path, index in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        if (bbox[2] - bbox[0]) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles periods, question marks, exclamation marks."""
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _check_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found. Install it:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Linux:  apt install ffmpeg\n"
            "  Perplexity Computer: pre-installed"
        )


def _pick_random_track() -> Path | None:
    tracks = list(AUDIO_DIR.glob("*.mp3"))
    return random.choice(tracks) if tracks else None


def _get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(audio_path)],
        capture_output=True, text=True, timeout=10,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 180.0


# --- Frame rendering ---

def _prepare_background(bg_path: str | Path) -> Image.Image | None:
    """Load a background and apply a legibility scrim.

    White type over photography needs the photograph pushed back or it becomes
    unreadable — the reference account drop-shadows for the same reason. Two
    passes: a flat dim across the whole frame so the type never fights a bright
    highlight, then a gradient weighted to the bottom where the type and CTA sit.
    """
    try:
        img = Image.open(bg_path).convert("RGB")
    except Exception as e:
        print(f"  Could not load background ({type(e).__name__}) — using plain card")
        return None

    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)

    # Flat dim over the whole frame
    img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), 0.28)

    # Bottom-weighted gradient: transparent at the top, ~72% black at the base.
    # Built as a one-pixel-wide column and stretched, which is far cheaper than
    # evaluating a per-pixel function over 2M pixels.
    ramp = Image.new("L", (1, HEIGHT))
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        # Quadratic ease so the darkening stays out of the subject's face
        ramp.putpixel((0, y), int(255 * 0.72 * (t ** 2.2)))
    mask = ramp.resize((WIDTH, HEIGHT))
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask)

    return img


def _render_frame(
    sentences: list[str],
    visible_up_to: int,
    fade_alpha: float,
    font: ImageFont.FreeTypeFont,
    brand_font: ImageFont.FreeTypeFont,
    cta_font: ImageFont.FreeTypeFont,
    line_height: int,
    wrapped_sentences: list[list[str]],
    y_start: int,
    show_cta: bool = False,
    cta_alpha: float = 0.0,
    progress: float = 0.0,
    background: Image.Image | None = None,
) -> bytes:
    """Render a single video frame and return raw RGB bytes.

    `background` is a pre-scrimmed 1080x1920 RGB image (see _prepare_background).
    It is copied per frame rather than drawn on, because the caller reuses one
    prepared background across every frame of the video.
    """
    if background is not None:
        img = background.copy()
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # No progress bar. A 3px bar across the top is a Shorts/TikTok UI convention
    # — it announces "content unit". A photograph does not have a progress bar.

    current_y = y_start

    for s_idx, lines in enumerate(wrapped_sentences):
        if s_idx > visible_up_to:
            break

        # Determine alpha for this sentence
        if s_idx < visible_up_to:
            alpha = 1.0
        else:
            alpha = fade_alpha

        # Every sentence the same white; only the fade differs
        v = int(255 * alpha)
        color = (v, v, v)

        for line in lines:
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
            x = (WIDTH - line_width) // 2
            if background is not None:
                # Per-glyph shadow. Over photography a scrim alone is not enough —
                # type crossing a light-to-dark edge loses its outline. Offset
                # copies behind the glyph keep it readable on any background, and
                # cost nothing on the plain-card path where they are skipped.
                shadow = (0, 0, 0)
                for dx, dy in ((3, 3), (-2, 2), (2, -2), (0, 4)):
                    draw.text((x + dx, current_y + dy), line, fill=shadow, font=font)
            draw.text((x, current_y), line, fill=color, font=font)
            current_y += line_height

        # Gap between sentences
        current_y += line_height // 2

    # Wordmark, not a call to action.
    #
    # This was "FOLLOW @MASTERINGMONEYXYZ", brightening at the end. A wordmark
    # builds a name; FOLLOW asks for a favour, and the reference account never
    # asks — it just signs the work. Constant and dim rather than pulsing,
    # because confidence reads better than urgency.
    mark_text = YOUTUBE_CHANNEL_NAME.upper()
    mark_bbox = cta_font.getbbox(mark_text)
    mark_width = mark_bbox[2] - mark_bbox[0]
    mark_x = (WIDTH - mark_width) // 2
    mark_y = HEIGHT - 250
    if background is not None:
        for dx, dy in ((2, 2), (-1, 1), (0, 3)):
            draw.text((mark_x + dx, mark_y + dy), mark_text, fill=(0, 0, 0), font=cta_font)
    draw.text((mark_x, mark_y), mark_text, fill=(150, 150, 150), font=cta_font)

    return img.tobytes()


def _mix_voice_and_music(
    voice_path: Path,
    music_path: Path | None,
    duration: int,
    output_path: Path,
) -> Path:
    """Mix voiceover with background music into a single audio file.

    Voice is full volume. Music is ducked to ~20% volume underneath.
    """
    if music_path is None:
        # No music — just use voice with padding to fill duration
        cmd = [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-af", f"apad=whole_dur={duration}",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        return output_path

    music_dur = _get_audio_duration(music_path)
    max_offset = max(0, music_dur - duration - 5)
    offset = random.uniform(0, max_offset) if max_offset > 0 else 0

    fade_out_start = max(0, duration - 1.5)

    # Mix: voice at full volume, music at 20% with fades
    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-ss", f"{offset:.1f}", "-i", str(music_path),
        "-filter_complex",
        # Pad voice to fill full duration
        f"[0:a]apad=whole_dur={duration}[voice];"
        # Music: volume down, trim, fade in/out
        f"[1:a]volume=0.18,"
        f"afade=t=in:st=0:d=0.5,"
        f"afade=t=out:st={fade_out_start}:d=1.5,"
        f"atrim=0:{duration}[music];"
        # Mix together
        f"[voice][music]amix=inputs=2:duration=first:dropout_transition=0[out]",
        "-map", "[out]",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=60)
    if result.returncode != 0:
        # Fallback: just use voice
        print(f"  Warning: audio mix failed, using voice only")
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-af", f"apad=whole_dur={duration}",
            "-c:a", "aac", "-b:a", "192k",
            str(output_path),
        ]
        subprocess.run(cmd_fallback, capture_output=True, timeout=30)

    return output_path


def create_video(
    text: str,
    voice_path: str | Path | None = None,
    duration: int | None = None,
    music_path: str | Path | None = None,
    filename: str | None = None,
    background_path: str | Path | None = None,
) -> Path:
    """Generate a YouTube Shorts video with sentence-by-sentence text reveal.

    Timeline (for 2-sentence quote, ~12s total):
      0.0s         : Sentence 1 appears INSTANTLY (no fade — hook)
      4.0s – 4.3s  : Sentence 2 fades in
      0.0s – end   : CTA subtle (opacity 55/255), brightens to full in last 2s
      @handle visible the whole time at bottom

    Voice + music mixed: voice at full volume, music bed at ~20%.
    Duration auto-calculated from voiceover length if provided.
    """
    _check_ffmpeg()

    duration = duration or YOUTUBE_VIDEO_DURATION
    if not filename:
        filename = f"short_{int(time.time())}.mp4"

    output_path = VIDEOS_DIR / filename

    # Pick background music
    if music_path is None:
        music_path = _pick_random_track()
    elif music_path:
        music_path = Path(music_path)

    # --- Determine duration from voiceover ---
    # If we have a voice track, set duration = voice length + 2s for CTA
    cta_duration = 2.0
    if voice_path:
        voice_path = Path(voice_path)
        voice_dur = _get_audio_duration(voice_path)
        # Duration = voice + CTA hold. Minimum 8s, cap at 15s.
        duration = max(8, min(15, int(voice_dur + cta_duration + 1.5)))
        print(f"  Voice: {voice_dur:.1f}s -> video: {duration}s")

    total_frames = duration * FPS

    # --- Layout calculation ---
    # Sentence case, not caps. Caps shout, and shouting is the visual grammar of
    # hustle content — the register our own theme scores rank worst. The LLM
    # already writes the quote in sentence case, so this is simply not destroying it.
    display_text = text
    sentences = _split_sentences(display_text)
    if not sentences:
        sentences = [display_text]

    padding = 80
    max_text_width = WIDTH - (padding * 2)

    # Find font size that fits — start large for maximum visual impact
    for font_size in range(72, 34, -2):
        font = _find_font(font_size)
        line_height = font_size + 22
        wrapped = [_wrap_text(s, font, max_text_width) for s in sentences]
        total_lines = sum(len(w) for w in wrapped) + len(wrapped) - 1
        total_text_height = total_lines * line_height
        if total_text_height <= 800:
            break

    # Pre-load fonts once
    brand_font = _find_font(32, FONT_CANDIDATES_LIGHT)
    cta_font = _find_font(36, FONT_CANDIDATES_BOLD)

    # Prepare the background once and reuse it for every frame — scrimming it
    # per frame would repeat the same work `duration * FPS` times.
    background = _prepare_background(background_path) if background_path else None

    # Text placement.
    #
    # On a plain card, centred is right — there is nothing to avoid. Over a
    # photograph it is wrong: centred type lands at roughly 41-55% of the frame,
    # which is exactly where the subject's face and torso are, while the quiet
    # lower third the prompt deliberately reserves sits empty. So when there is a
    # background, anchor the block's BASE just above the CTA and let it grow
    # upward — type over the subject's body and ground, never over the face.
    if background is not None:
        y_start = (HEIGHT - 420) - total_text_height
    else:
        y_start = (HEIGHT - total_text_height) // 2 - 40

    # --- Timeline ---
    num_sentences = len(sentences)
    fade_duration = 0.3  # fast fade for sentence 2+

    # Sentence 1 is instant (visible at frame 0).
    # Sentence 2+ appears at 4s intervals.
    time_per_sentence = 4.0

    # CTA appears in last 2 seconds
    cta_start = duration - cta_duration

    # --- Mix audio ---
    mixed_audio_path = None
    if voice_path or music_path:
        mixed_audio_path = VIDEOS_DIR / f"_mix_{int(time.time())}.m4a"
        if voice_path:
            _mix_voice_and_music(voice_path, music_path, duration, mixed_audio_path)
            if music_path:
                print(f"  Music: {Path(music_path).stem} (bed at 18%)")
        else:
            # Music only (no voice) — full volume with fades
            music_path = Path(music_path)
            music_dur = _get_audio_duration(music_path)
            max_offset = max(0, music_dur - duration - 5)
            offset = random.uniform(0, max_offset) if max_offset > 0 else 0
            fade_out_start = max(0, duration - 1.5)
            cmd_music = [
                "ffmpeg", "-y",
                "-ss", f"{offset:.1f}", "-i", str(music_path),
                "-af",
                f"afade=t=in:st=0:d=0.5,"
                f"afade=t=out:st={fade_out_start}:d=1.5,"
                f"atrim=0:{duration}",
                "-c:a", "aac", "-b:a", "192k",
                str(mixed_audio_path),
            ]
            subprocess.run(cmd_music, capture_output=True, timeout=30)
            print(f"  Music: {music_path.stem} (no voice)")

    # --- Build ffmpeg command ---
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",  # stdin for video frames
    ]

    if mixed_audio_path and mixed_audio_path.exists():
        cmd.extend(["-i", str(mixed_audio_path)])
        cmd.extend(["-c:a", "copy"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "medium",
        "-crf", "23",
        "-movflags", "+faststart",
        "-t", str(duration),
        "-shortest",
        str(output_path),
    ])

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # --- Render each frame ---
    for frame_num in range(total_frames):
        t = frame_num / FPS

        # Sentence visibility logic:
        # Sentence 0 is INSTANT — visible at full alpha from frame 0
        # Sentence 1+ fades in at time_per_sentence intervals
        visible_up_to = 0
        fade_alpha = 1.0

        if num_sentences == 1:
            visible_up_to = 0
            fade_alpha = 1.0
        else:
            # Sentence 0 always fully visible
            visible_up_to = 0
            fade_alpha = 1.0

            for s_idx in range(1, num_sentences):
                sentence_start = s_idx * time_per_sentence
                sentence_fade_end = sentence_start + fade_duration

                if t >= sentence_fade_end:
                    visible_up_to = s_idx
                    fade_alpha = 1.0
                elif t >= sentence_start:
                    visible_up_to = s_idx
                    fade_alpha = (t - sentence_start) / fade_duration
                    break
                else:
                    break

        # CTA in last 2 seconds
        show_cta = t >= cta_start
        cta_alpha = min(1.0, (t - cta_start) / 0.4) if show_cta else 0.0

        progress = (frame_num + 1) / total_frames

        frame_bytes = _render_frame(
            sentences=sentences,
            visible_up_to=visible_up_to,
            fade_alpha=fade_alpha,
            font=font,
            brand_font=brand_font,
            cta_font=cta_font,
            line_height=line_height,
            wrapped_sentences=wrapped,
            y_start=y_start,
            show_cta=show_cta,
            cta_alpha=cta_alpha,
            progress=progress,
            background=background,
        )
        try:
            proc.stdin.write(frame_bytes)
        except (BrokenPipeError, OSError):
            break

    try:
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    proc.stdin = None

    _, stderr = proc.communicate()

    # Clean up temp audio
    if mixed_audio_path and mixed_audio_path.exists():
        try:
            mixed_audio_path.unlink()
        except OSError:
            pass

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr.decode()[-1000:]}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  Video: {output_path.name} ({size_mb:.1f} MB, {duration}s)")
    return output_path
