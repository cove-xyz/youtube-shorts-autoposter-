"""Instagram carousels — the Based-Living-style feed post.

A different content product from the Short, not a reformat of one. The Short is a
volume play into an algorithmic feed; the carousel is a depth play into a grid.

Three decisions that came out of studying the reference account, each of which
contradicts something obvious:

  SAME LINE ON EVERY SLIDE, not a build-to-payoff. Splitting a sentence across
  slides imports video logic — hook, then reveal over time — into a format nobody
  swipes for that reason. Once read on slide one the line becomes furniture, a
  frame around the image, and the eye goes to the photograph on every slide after.
  That is what lets the images carry the post.

  BESPOKE LINE EACH TIME, not a recurring franchise stamp. The reference account
  reuses "I must live a certain way" on roughly 38% of posts, and those posts have
  a median of ~2,500 likes against ~5,900 for posts with a written-for-this-one
  line. Repetition across slides is the format; repetition across posts is a tax.

  4:5, NOT 9:16. Feed posts crop to 4:5, and the Short's composition rule reserves
  the lower half of a tall frame for type — geometry that does not survive the
  aspect change, so the images are generated for this shape rather than cropped
  down from the Short's.

The caption is a separate beat handled by caption_generator: it turns on the line
rather than restating it, which is where the account's voice actually lives.
"""
import re
import time

import requests
from pathlib import Path

from PIL import Image, ImageDraw

from src.config import IMAGES_DIR
from src.image_engine import (
    HOUSE_STYLE,
    THEME_SUBJECTS,
    _crop_to_frame,
    _generate_openrouter,
    _subject_brief,
    passes_quality_gate,
    vision_score,
)
from src.video_generator import _find_font, _wrap_text

WIDTH, HEIGHT = 1080, 1350  # 4:5, the tallest ratio Instagram shows in feed
# Four, not five: one rejection is common and the set reads fine at four,
# while a fifth generation is a straight 20% cost add on the biggest line item.
SLIDES = 4

# The Short reserves the lower HALF of a 9:16 frame. A 4:5 frame is far less tall,
# so the same instruction would squeeze the subject into a strip. Here the type
# sits across the lower third and the face is asked to stay clear of it.
COMPOSITION_45 = (
    "Vertical 4:5 frame. The subject's face is in the UPPER THIRD and fully visible. "
    "The BOTTOM THIRD holds body, clothing, ground, wall or water — broad simple "
    "shapes, low detail, no bright highlights, no small busy texture and no "
    "lettering, so large type can be laid over it and stay readable."
)


def _build_prompt(subject: str) -> str:
    return f"{subject}. {HOUSE_STYLE} {COMPOSITION_45}"


def _scrim(img: Image.Image) -> Image.Image:
    """Flat dim plus a bottom-weighted gradient, tuned for 4:5.

    Shallower than the Short's scrim: in a 4:5 frame the type occupies a larger
    share of the picture, so the same darkening would flatten the photograph.
    """
    img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), 0.22)
    ramp = Image.new("L", (1, HEIGHT))
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        ramp.putpixel((0, y), int(255 * 0.68 * (t ** 2.0)))
    mask = ramp.resize((WIDTH, HEIGHT))
    return Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, mask)


def _stamp(img: Image.Image, line: str) -> Image.Image:
    """Lay the line across the lower third, identically on every slide."""
    draw = ImageDraw.Draw(img)
    padding = 72
    max_w = WIDTH - padding * 2

    for size in range(64, 30, -2):
        font = _find_font(size)
        lines = _wrap_text(line, font, max_w)
        lh = size + 14
        if len(lines) * lh <= 420 and len(lines) <= 5:
            break

    total = len(lines) * lh
    y = HEIGHT - 150 - total  # base sits above the wordmark

    for text in lines:
        bbox = font.getbbox(text)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        for dx, dy in ((3, 3), (-2, 2), (2, -2), (0, 4)):
            draw.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        y += lh

    from src.config import YOUTUBE_CHANNEL_NAME
    mark_font = _find_font(26)
    mark = YOUTUBE_CHANNEL_NAME.upper()
    mb = mark_font.getbbox(mark)
    mx = (WIDTH - (mb[2] - mb[0])) // 2
    for dx, dy in ((2, 2), (0, 3)):
        draw.text((mx + dx, HEIGHT - 92 + dy), mark, fill=(0, 0, 0), font=mark_font)
    draw.text((mx, HEIGHT - 92), mark, fill=(150, 150, 150), font=mark_font)
    return img


def _fit(img: Image.Image) -> Image.Image:
    """Cover-fit an arbitrary generation to 4:5."""
    global WIDTH, HEIGHT
    from src import image_engine as ie
    prev = (ie.WIDTH, ie.HEIGHT)
    ie.WIDTH, ie.HEIGHT = WIDTH, HEIGHT
    try:
        return _crop_to_frame(img)
    finally:
        ie.WIDTH, ie.HEIGHT = prev


def _carousel_subjects(quote: str, theme: str, n: int) -> list[str]:
    """N distinct moments sharing ONE setting.

    Generated in a single call rather than n independent briefs. Asking per-slide
    for "another moment in the same place" anchors nothing: the first attempt gave
    the same man in the same pose against a wall in daylight on one slide and
    beside water at night on the next. Same prompt run five times is not a
    carousel — the set has to read as one world, which means the setting must be
    decided once and the variation must be in what happens inside it.
    """
    fallback = [THEME_SUBJECTS.get(theme, THEME_SUBJECTS["discipline"])] * n
    try:
        from src.llm import generate

        raw = generate(
            f'You are casting a {n}-photograph sequence to sit behind this line:\n\n'
            f'"{quote}"\n\n'
            "First work out what the line is actually ABOUT — the human situation "
            "underneath it, not the objects it happens to mention. A line using the "
            "word 'clothes' to talk about a broken promise is about the promise, not "
            "about clothes; photographing a suitcase would be a literal reading of a "
            "figurative line, and the set would not make sense next to the words.\n\n"
            f"Then choose ONE specific place and ONE person for THAT situation, and "
            f"describe {n} different moments there. Rules:\n"
            "- Every moment is in the SAME place, same light, same day. The set must "
            "read as one afternoon, not five locations.\n"
            "- Each moment shows something DIFFERENT happening: a different action, a "
            "different distance (tight on the face and shoulders, wide across the "
            "room), a different part of the task.\n"
            "- Real physical work or effort. Never charts, money, screens or offices.\n"
            "- Show the WHOLE PERSON or their upper body. Do NOT write close-ups of "
            "hands or fingers: generated hands come out malformed and get rejected.\n"
            "- Avoid objects that carry printed labels or writing (tins, packaging, "
            "signage, branded wraps) — any lettering in frame is an automatic reject.\n"
            "- Name the place in every line so it stays fixed.\n"
            "- Under 20 words each. No camera settings, no era, no art direction.\n\n"
            f"Return exactly {n} lines, numbered 1. to {n}. Nothing else.",
            max_tokens=90 * n,
        )
        out = []
        for line in raw.splitlines():
            line = re.sub(r"^\s*(?:\d+\s*[.)\-:]|[-*•])\s*", "", line.strip()).strip()
            # Models return markdown here; asterisks would go straight into the
            # image prompt as literal characters.
            line = line.replace("**", "").replace("__", "").replace("*", "").strip()
            if 10 <= len(line) <= 200 and line not in out:
                out.append(line)
        if len(out) >= max(3, n - 1):
            return out[:n]
        print(f"    (only {len(out)} usable subjects parsed, using theme default)")
    except Exception as e:
        print(f"    (subject sequence failed: {type(e).__name__})")
    return fallback


CAROUSEL_RUBRIC = """You are reviewing a finished Instagram carousel before it publishes unseen.

You are given every slide in order, the line printed on all of them, and the caption.

Judge three things the per-slide checks cannot see:

1. COHERENCE. Do these read as one place, one person, one day? A set that jumps
   location, time of day or subject looks like the same prompt run N times rather
   than a sequence. This is the most common failure.

2. LEAD. Which slide should come FIRST? Slide one is the grid thumbnail and the
   only frame most people ever see, so it must be the strongest image on its own,
   with the clearest subject and the most readable type. It is often not the slide
   that happens to be first.

3. CAPTION. Does the caption connect to the line and the images? It should land a
   second, different beat — not restate the line, but not be a non-sequitur either.
   A caption about a gym under photographs of someone packing a suitcase is a miss.

Reply in exactly this format, nothing else:
COHERENT: <yes|no>
LEAD: <slide number>
CAPTION_OK: <yes|no>
SCORE: <0-10 for the set as a whole>
REASON: <one short sentence>"""


def judge_carousel(paths: list[Path], line: str, caption: str) -> dict:
    """Review the finished set as a whole. Returns verdict fields.

    Distinct from the per-slide vision gate, which only ever sees one image and so
    cannot judge whether four of them belong together, which should lead, or
    whether the caption connects to anything. Fails open — a review outage should
    cost us the ordering, not the post.
    """
    from src.config import OPENROUTER_API_KEY, VISION_MODEL
    from src.image_engine import _encode_jpeg

    default = {"coherent": True, "lead": 1, "caption_ok": True, "score": 5,
               "reason": "not reviewed"}
    if not OPENROUTER_API_KEY or not paths:
        return default

    content: list = [{"type": "text", "text":
                      f"{CAROUSEL_RUBRIC}\n\nLINE ON EVERY SLIDE: {line}\nCAPTION: {caption}"}]
    for i, p in enumerate(paths, 1):
        content.append({"type": "text", "text": f"Slide {i}:"})
        content.append({"type": "image_url", "image_url": {
            "url": f"data:image/jpeg;base64,{_encode_jpeg(Image.open(p))}"}})

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json={"model": VISION_MODEL, "max_tokens": 160,
                  "messages": [{"role": "user", "content": content}]},
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, timeout=120)
        if r.status_code >= 400:
            print(f"    carousel judge HTTP {r.status_code}: {r.text[:160]}")
            return default
        text = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    carousel judge failed ({type(e).__name__}) — not blocking")
        return default

    out = dict(default)
    for ln in text.splitlines():
        k, _, v = ln.partition(":")
        k, v = k.strip().upper(), v.strip()
        if k == "COHERENT":
            out["coherent"] = v.lower().startswith("y")
        elif k == "LEAD":
            digits = "".join(c for c in v if c.isdigit())
            if digits:
                out["lead"] = max(1, min(len(paths), int(digits[:2])))
        elif k == "CAPTION_OK":
            out["caption_ok"] = v.lower().startswith("y")
        elif k == "SCORE":
            digits = "".join(c for c in v if c.isdigit())
            if digits:
                out["score"] = max(0, min(10, int(digits[:2])))
        elif k == "REASON":
            out["reason"] = v[:140]
    return out


def build_carousel(quote: str, theme: str, slides: int = SLIDES) -> dict | None:
    """Render a full carousel. Returns {paths, line, subjects} or None.

    Each slide gets its own subject so the set reads as a sequence of moments in
    one world rather than N takes of one photograph. The shared grade comes from
    HOUSE_STYLE, which is the same constant the Shorts use — coherence across both
    products, and across the grid, is the whole reason it is locked.
    """
    print(f"  Building {slides}-slide carousel...")
    paths: list[Path] = []
    stamp_batch = int(time.time())

    subjects = _carousel_subjects(quote, theme, slides)
    # Accumulate into a SEPARATE list. Appending to `subjects` inside this loop
    # grew the list being iterated and never terminated — it ran to 37 slides
    # before the timeout, at $0.04 a generation.
    used: list[str] = []
    for i, subject in enumerate(subjects):
        images = _generate_openrouter(_build_prompt(subject), n=1, aspect_ratio="4:5")
        if not images:
            print(f"    slide {i + 1}: generation failed, skipping")
            continue

        framed = _fit(images[0])
        ok, why = passes_quality_gate(framed)
        if not ok:
            print(f"    slide {i + 1}: rejected — {why}")
            continue
        score, reason = vision_score(framed)
        if score < 4:
            print(f"    slide {i + 1}: rejected — {score}/10 {reason}")
            continue

        out = IMAGES_DIR / f"car_{stamp_batch}_{i + 1}.jpg"
        _stamp(_scrim(framed), quote).save(out, "JPEG", quality=92)
        paths.append(out)
        used.append(subject)
        print(f"    slide {i + 1}: {score}/10  {subject[:56]}")

    # A carousel of one is just a single image post, and a thin one at that
    if len(paths) < 3:
        print(f"  Only {len(paths)} usable slides — abandoning carousel")
        return None

    return {"paths": paths, "line": quote, "subjects": used}
