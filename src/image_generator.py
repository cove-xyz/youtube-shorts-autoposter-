import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGES_DIR, YOUTUBE_CHANNEL_NAME

# Font priority: heavy/bold condensed > bold sans > fallback
# We want fonts that look aggressive and powerful in ALL CAPS
FONT_CANDIDATES_BOLD = [
    # macOS — strong, heavy fonts first
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 4),   # Futura Condensed ExtraBold
    ("/System/Library/Fonts/Supplemental/Impact.ttf", 0),
    ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 2),   # Futura Bold
    # Linux (Perplexity Computer / Docker)
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
]

FONT_CANDIDATES_LIGHT = [
    # For brand watermark — lighter weight
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
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0]
        if line_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


# --- Instagram ---

def generate_feed_image(text: str, filename: str | None = None) -> Path:
    """Generate a 1080x1080 feed post image. Black bg, white ALL CAPS text."""
    width, height = 1080, 1080
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    display_text = text.upper()

    padding = 100
    max_text_width = width - (padding * 2)
    max_text_height = height - 300

    for font_size in range(52, 24, -2):
        font = _find_font(font_size)
        lines = _wrap_text(display_text, font, max_text_width)
        line_height = font_size + 16
        total_height = len(lines) * line_height
        if total_height <= max_text_height and len(lines) <= 5:
            break

    y_start = (height - total_height) // 2 - 30

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = y_start + i * line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=font)

    brand_font = _find_font(18, FONT_CANDIDATES_LIGHT)
    brand_text = "MASTERING MONEY"
    brand_bbox = brand_font.getbbox(brand_text)
    brand_width = brand_bbox[2] - brand_bbox[0]
    draw.text(
        (width - brand_width - 40, height - 50),
        brand_text,
        fill=(120, 120, 120),
        font=brand_font,
    )

    if not filename:
        filename = f"feed_{int(time.time())}.png"

    path = IMAGES_DIR / filename
    img.save(str(path), "PNG")
    return path


def generate_story_image(text: str, filename: str | None = None) -> Path:
    """Generate a 1080x1920 story image. Black bg, white ALL CAPS text."""
    width, height = 1080, 1920
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    display_text = text.upper()

    padding = 80
    max_text_width = width - (padding * 2)

    for font_size in range(60, 28, -2):
        font = _find_font(font_size)
        lines = _wrap_text(display_text, font, max_text_width)
        line_height = font_size + 20
        total_height = len(lines) * line_height
        if total_height <= 600 and len(lines) <= 4:
            break

    y_start = (height - total_height) // 2 - 50

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = y_start + i * line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=font)

    brand_font = _find_font(16, FONT_CANDIDATES_LIGHT)
    brand_text = "MASTERING MONEY"
    brand_bbox = brand_font.getbbox(brand_text)
    brand_width = brand_bbox[2] - brand_bbox[0]
    draw.text(
        (width - brand_width - 40, height - 60),
        brand_text,
        fill=(100, 100, 100),
        font=brand_font,
    )

    if not filename:
        filename = f"story_{int(time.time())}.png"

    path = IMAGES_DIR / filename
    img.save(str(path), "PNG")
    return path


# --- YouTube ---

def generate_youtube_image(text: str, filename: str | None = None) -> Path:
    """Generate a 1080x1920 YouTube Shorts image.

    Pure black background. White ALL CAPS text. Heavy bold font.
    Centered brand watermark below.
    """
    width, height = 1080, 1920
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    display_text = text.upper()

    # --- Quote text ---
    padding = 80
    max_text_width = width - (padding * 2)

    for font_size in range(62, 28, -2):
        font = _find_font(font_size)
        lines = _wrap_text(display_text, font, max_text_width)
        line_height = font_size + 26
        total_height = len(lines) * line_height
        if total_height <= 700 and len(lines) <= 6:
            break

    # Center text vertically, shifted slightly up
    y_start = (height - total_height) // 2 - 60

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = y_start + i * line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=font)

    # --- Handle centered, above mobile player controls ---
    brand_font = _find_font(32, FONT_CANDIDATES_LIGHT)
    brand_text = "@MASTERINGMONEYXYZ"
    brand_bbox = brand_font.getbbox(brand_text)
    brand_width = brand_bbox[2] - brand_bbox[0]
    draw.text(
        ((width - brand_width) // 2, height - 300),
        brand_text,
        fill=(80, 80, 80),
        font=brand_font,
    )

    if not filename:
        filename = f"yt_{int(time.time())}.png"

    path = IMAGES_DIR / filename
    img.save(str(path), "PNG")
    return path
