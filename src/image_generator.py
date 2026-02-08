import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from src.config import IMAGES_DIR

# Attempt to use Courier/Monaco, fall back to default
FONT_CANDIDATES = [
    "/System/Library/Fonts/Courier.dfont",
    "/System/Library/Fonts/Monaco.dfont",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
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


def generate_feed_image(text: str, filename: str | None = None) -> Path:
    """Generate a 1080x1080 feed post image."""
    width, height = 1080, 1080
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Main text - start large, scale down if needed
    padding = 100
    max_text_width = width - (padding * 2)
    max_text_height = height - 300  # leave room for branding

    for font_size in range(52, 24, -2):
        font = _find_font(font_size)
        lines = _wrap_text(text, font, max_text_width)

        # Calculate total height
        line_height = font_size + 16
        total_height = len(lines) * line_height

        if total_height <= max_text_height and len(lines) <= 5:
            break

    # Center text vertically (slightly above center)
    y_start = (height - total_height) // 2 - 30

    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) // 2
        y = y_start + i * line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=font)

    # Branding - bottom right
    brand_font = _find_font(18)
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
        import time
        filename = f"feed_{int(time.time())}.png"

    path = IMAGES_DIR / filename
    img.save(str(path), "PNG")
    return path


def generate_story_image(text: str, filename: str | None = None) -> Path:
    """Generate a 1080x1920 story image."""
    width, height = 1080, 1920
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)

    padding = 80
    max_text_width = width - (padding * 2)

    for font_size in range(60, 28, -2):
        font = _find_font(font_size)
        lines = _wrap_text(text, font, max_text_width)
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

    # Branding
    brand_font = _find_font(16)
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
        import time
        filename = f"story_{int(time.time())}.png"

    path = IMAGES_DIR / filename
    img.save(str(path), "PNG")
    return path
