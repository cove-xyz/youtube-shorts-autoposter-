"""YouTube Shorts video generator.

Renders frames in Python (Pillow) with sentence-by-sentence text reveal,
then pipes raw frames to ffmpeg for encoding with voice + music.

The visual style:
- 1080x1920 pure black background
- White ALL CAPS text, heavy bold font
- Sentence 1 appears INSTANTLY at frame 0 (no fade — hook the viewer)
- Sentence 2 fades in at ~4s
- CTA "FOLLOW @masteringmoneyxyz" subtle from start, bright in last 2s
- @masteringmoneyxyz watermark visible the entire time
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
    YOUTUBE_VIDEO_DURATION,
    YOUTUBE_HANDLE,
)

WIDTH, HEIGHT = 1080, 1920
FPS = 24

# --- Font loading ---

FONT_CANDIDATES_BOLD = [
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 4),   # Futura Condensed ExtraBold
    ("/System/Library/Fonts/Supplemental/Impact.ttf", 0),
    ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 2),   # Futura Bold
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
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
) -> bytes:
    """Render a single video frame and return raw RGB bytes."""
    img = Image.new("RGB", (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    current_y = y_start

    for s_idx, lines in enumerate(wrapped_sentences):
        if s_idx > visible_up_to:
            break

        # Determine alpha for this sentence
        if s_idx < visible_up_to:
            alpha = 1.0
        else:
            alpha = fade_alpha

        color_val = int(255 * alpha)
        color = (color_val, color_val, color_val)

        for line in lines:
            bbox = font.getbbox(line)
            line_width = bbox[2] - bbox[0]
            x = (WIDTH - line_width) // 2
            draw.text((x, current_y), line, fill=color, font=font)
            current_y += line_height

        # Gap between sentences
        current_y += line_height // 2

    # CTA: "FOLLOW FOR MORE" — subtle from start, brightens in last 2 seconds
    cta_text = f"FOLLOW {YOUTUBE_HANDLE.upper()}"
    cta_bbox = cta_font.getbbox(cta_text)
    cta_width = cta_bbox[2] - cta_bbox[0]
    if show_cta:
        # Last 2 seconds: bright white
        cta_val = int(255 * cta_alpha)
    else:
        # Rest of video: subtle hint
        cta_val = 55
    draw.text(
        ((WIDTH - cta_width) // 2, HEIGHT - 420),
        cta_text,
        fill=(cta_val, cta_val, cta_val),
        font=cta_font,
    )

    # Handle watermark — always visible, above mobile player controls
    handle_text = YOUTUBE_HANDLE.upper()
    brand_bbox = brand_font.getbbox(handle_text)
    brand_width = brand_bbox[2] - brand_bbox[0]
    draw.text(
        ((WIDTH - brand_width) // 2, HEIGHT - 300),
        handle_text,
        fill=(80, 80, 80),
        font=brand_font,
    )

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
    display_text = text.upper()
    sentences = _split_sentences(display_text)
    if not sentences:
        sentences = [display_text]

    padding = 80
    max_text_width = WIDTH - (padding * 2)

    # Find font size that fits all sentences
    for font_size in range(58, 28, -2):
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

    # Center vertically
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
