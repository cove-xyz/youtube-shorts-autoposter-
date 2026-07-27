"""Generated photographic backgrounds for Shorts frames.

Until now every frame was white type on `Image.new(black)` — no photograph at
all, which puts us at the far end of the objects-vs-faces spectrum that
correlates with the worst-performing content on comparable accounts. This module
generates a background so the type has something to sit on.

The thing being reproduced is NOT photorealism, it is **provenance**: an image
that reads as though it were taken for some other reason and found later, rather
than produced on request. That is a property of visual cues — grain structure,
available light, awkward framing, a subject mid-gesture — so it is a prompting
target, not a model limitation.

Two constants below carry the whole design:

  HOUSE_STYLE     Locked treatment. Era is deliberately NOT specified: a 2026
                  press photo and a 1974 magazine frame both read as "found" if
                  the grade and framing are right, so fixing the treatment
                  (rather than the decade) buys coherence across 150 images a
                  month while still allowing modern subjects.

  COMPOSITION     Reserves a quiet lower third for the type. This is what makes
                  carousels possible later: the reference account stamps the same
                  line onto every slide of a set, which only works if every image
                  has usable negative space in the SAME place. Getting that
                  constraint in now means multi-slide output is not a rewrite.
"""
import base64
import io
import random
import time

import requests
from PIL import Image, ImageStat

from src.config import (
    IMAGES_DIR,
    IMAGE_CANDIDATES,
    IMAGE_MODEL,
    IMAGE_PROVIDER,
    OPENROUTER_API_KEY,
    VISION_GATE_ENABLED,
    VISION_MODEL,
)

# Below this the frame is discarded rather than published. 4 lets a plausible
# but generic photograph through while blocking the 0-3 band — no human, broken
# anatomy, stray lettering, obvious AI tells.
VISION_MIN_SCORE = 4

WIDTH, HEIGHT = 1080, 1920

# Locked treatment — see module docstring. Do not add an era here.
HOUSE_STYLE = (
    "Documentary photograph, not a studio portrait. Available light only, no studio "
    "lighting. Visible 35mm film grain, slightly muted contrast, colours a little "
    "desaturated. The subject is absorbed in what they are doing and has not noticed "
    "the photographer: their gaze is directed down or away at their own hands or task, "
    "never toward the lens, and they are mid-movement rather than holding still. "
    "Framing is slightly off-centre, as though cropped from a wider original. "
    "Incidental background detail, other people partly visible at the edges of frame. "
    "Avoid symmetry, avoid heavy background blur, avoid glossy retouching, avoid "
    "flawless skin, avoid anything that looks staged or advertised."
)

# Reserves type space. Load-bearing for legibility now and carousels later.
#
# Deliberately NOT "leave the lower third empty" — that squeezes the subject into
# the top half and produces dead, badly-composed frames. The reference account
# lays type straight over the subject's body and keeps only the face clear, so
# that is what this asks for: face high, lower half low-detail but still part of
# the picture. Legibility over the body comes from the scrim plus the per-glyph
# shadow in the renderer, not from empty space.
COMPOSITION = (
    "Vertical 9:16 frame. The subject's face is in the UPPER HALF of the frame and is "
    "fully visible. The LOWER HALF holds the subject's body, clothing, ground, wall or "
    "water — broad simple shapes, low detail, no bright highlights, no small busy "
    "texture and no lettering, so that large type can be laid over it and stay readable."
)

NEGATIVE = (
    "text, lettering, watermark, signature, logo, caption, subtitles, borders, "
    "collage, split screen, illustration, 3d render, cartoon, oversaturated, "
    "symmetrical composition, eye contact with camera, looking at camera, "
    "posing for the camera, portrait pose, stock photo"
)

# Fallback subjects per theme, used when the brief-writing call fails. Chosen for
# character-over-calculation: working people and physical effort, never charts,
# tickers, cash or office interiors — the register that correlates with the worst
# conversion in our own theme scores.
THEME_SUBJECTS = {
    "wealth_building": "a tradesman in his forties resting against a workbench at the end of a shift",
    "discipline": "a boxer alone in an empty gym, wrapping his hands, mid-motion",
    "mindset": "a lone fisherman hauling a line on a small boat in flat grey light",
    "investing": "an older man at a kitchen table with paperwork, mid-thought, looking away",
    "entrepreneurship": "a woman opening the shutters of her own small shop before dawn",
    "autonomy": "a man swimming alone off a rocky coast at first light",
    "productivity": "a mechanic under a raised car, arms up, caught mid-task",
    "leadership": "a foreman on a building site talking to two workers, gesturing",
    "stoicism": "a stonemason chipping at a block, dust in the air, face half turned",
    "self_improvement": "a runner stopped on a hill road at dusk, hands on knees, breathing hard",
}


def _subject_brief(quote: str, theme: str) -> str:
    """Ask the LLM for a subject matched to this specific line.

    Deliberately a separate call rather than an extra field on the quote prompt:
    quote generation is load-bearing and was only just repaired, so it does not
    get a new output format to parse. A failure here costs a themed default, not
    a post.
    """
    fallback = THEME_SUBJECTS.get(theme, THEME_SUBJECTS["discipline"])
    try:
        from src.llm import generate

        brief = generate(
            "You are casting a single photograph to sit behind this line of text:\n\n"
            f'"{quote}"\n\n'
            "Describe ONE human subject for that photograph in under 20 words.\n"
            "Rules:\n"
            "- A real person doing something physical, caught mid-action.\n"
            "- Never charts, graphs, money, screens, offices, or luxury objects.\n"
            "- Do not restate or quote the line. Describe only what is in frame.\n"
            "- No camera settings, no art direction, no era. Subject only.\n\n"
            "Return only the description.",
            max_tokens=60,
        )
        brief = brief.strip().strip('"').split("\n")[0].strip()
        # A refusal or a restatement of the quote is worse than the default
        if 8 <= len(brief) <= 200 and quote[:20].lower() not in brief.lower():
            return brief
    except Exception as e:
        print(f"    (subject brief failed, using theme default: {type(e).__name__})")
    return fallback


def build_prompt(subject: str) -> str:
    """Assemble the full generation prompt: subject + locked house style."""
    return f"{subject}. {HOUSE_STYLE} {COMPOSITION}"


def _crop_to_frame(img: Image.Image) -> Image.Image:
    """Cover-fit to 1080x1920, cropping off-centre.

    Generating wider than needed and cropping off-centre is a cheap provenance
    cue: a crop implies an original that extended past the frame.
    """
    target = WIDTH / HEIGHT
    w, h = img.size
    if w / h > target:
        new_w = int(h * target)
        # Off-centre rather than centred — a centred crop reads as composed
        max_off = w - new_w
        left = int(max_off * random.uniform(0.25, 0.75)) if max_off > 0 else 0
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target)
        max_off = h - new_h
        top = int(max_off * random.uniform(0.0, 0.4)) if max_off > 0 else 0
        img = img.crop((0, top, w, top + new_h))
    return img.resize((WIDTH, HEIGHT), Image.LANCZOS)


def passes_quality_gate(img: Image.Image) -> tuple[bool, str]:
    """Cheap pixel checks for the failures that would ship a broken post.

    Nothing here judges whether the photograph is *good* — it catches blank,
    near-uniform, or top-heavy-bright frames that would make the overlaid type
    unreadable. A vision-model check on subject and credibility is the natural
    next step; this is the floor, not the ceiling.
    """
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)

    # A near-uniform frame means the generation collapsed
    if stat.stddev[0] < 12:
        return False, f"near-uniform image (stddev {stat.stddev[0]:.1f})"

    # The lower half carries the type — boundary matches COMPOSITION and the
    # renderer's text placement, so all three agree on where type goes
    lower = gray.crop((0, int(HEIGHT * 0.52), WIDTH, HEIGHT))
    upper = gray.crop((0, 0, WIDTH, int(HEIGHT * 0.52)))
    lower_mean = ImageStat.Stat(lower).mean[0]
    upper_mean = ImageStat.Stat(upper).mean[0]

    if lower_mean > 165:
        return False, f"lower third too bright for type (mean {lower_mean:.0f})"
    if lower_mean > upper_mean + 25:
        return False, "lower third brighter than subject area"

    return True, "ok"


def _generate_openrouter(prompt: str, n: int = 1, aspect_ratio: str = "9:16") -> list[Image.Image]:
    """Generate n candidates via OpenRouter's Image API. Returns [] on failure.

    The payload is kept in one place because parameter support varies per model
    on OpenRouter (`supported_parameters` in their discovery API) — if a swap of
    IMAGE_MODEL rejects a field, this dict is the only thing to edit, and
    `verify_image_engine()` prints the rejection verbatim.
    """
    if not OPENROUTER_API_KEY:
        print("    OPENROUTER_API_KEY not set")
        return []

    payload = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": n,
        # `resolution` is deliberately omitted rather than pinned. Models enforce
        # their own minimum output pixels (Seedream 4.5 rejects "2K" at 9:16 as
        # too small), and the default always satisfies that. We crop to 1080x1920
        # regardless, so anything at or above that is enough — leaving it unset
        # keeps this payload portable across models.
        # Was hardcoded to 9:16. Carousels then asked for a 4:5 composition in
        # the prompt while generating 9:16 and cropping a third away — the model
        # was composing for a frame that never shipped.
        "aspect_ratio": aspect_ratio,
        "output_format": "jpeg",
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/images",
            json=payload, headers=headers, timeout=180,
        )
    except requests.RequestException as e:
        print(f"    request failed: {type(e).__name__}")
        return []

    if resp.status_code >= 400:
        # Verbatim: a parameter the model does not support shows up here
        print(f"    HTTP {resp.status_code}: {resp.text[:400]}")
        return []

    body = resp.json()
    cost = (body.get("usage") or {}).get("cost")
    if cost is not None:
        print(f"    generation cost: ${cost:.4f}")

    images = []
    for item in body.get("data") or []:
        b64 = item.get("b64_json")
        if not b64:
            continue
        try:
            images.append(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB"))
        except Exception as e:
            print(f"    could not decode image: {type(e).__name__}")

    if not images:
        print(f"    no images in response (keys: {list(body.keys())})")
    return images


def _encode_jpeg(img: Image.Image, max_edge: int = 768) -> str:
    """Downscale and base64-encode for the vision call.

    768px is plenty to judge composition, anatomy and stray text, and keeps the
    vision call cheap — sending the full 1080x1920 would multiply image tokens
    for no extra signal.
    """
    small = img.copy()
    small.thumbnail((max_edge, max_edge), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


VISION_RUBRIC = """You are checking one generated photograph before it is published unreviewed.

Answer with a score and a reason, in exactly this format:
SCORE: <0-10>
REASON: <one short sentence>

IMPORTANT: other people partly visible in the background are INTENTIONAL and must
NOT lower the score. They are wanted. Only treat people as a problem if two or more
compete as the main subject of the photograph.

Score 0-3 if ANY of these are true:
- No person in the frame at all
- Visibly wrong anatomy: malformed hands, extra or missing limbs, distorted face
- Any lettering, watermark, logo or signature anywhere in the image
- The main subject's face is cut off, or sits below the vertical midpoint of the frame
- It reads as an obvious AI generation: plastic skin, impossible light, dreamlike mush

Score 4-6 if it is a plausible photograph but ANY of these apply:
- The subject is looking into the camera lens, or is posed and holding still for it
- It feels staged, advertised, or like generic stock photography
- The lower half is too visually busy or too bright for large white text to sit on it

Score 7-10 only if it reads as a real documentary photograph someone actually took:
the subject is mid-action and NOT looking at the lens, light and grain are believable,
the face is clearly in the upper half, and the lower half is simple enough to carry
overlaid text."""


def vision_score(img: Image.Image) -> tuple[int, str]:
    """Have a multimodal model look at the frame. Returns (score 0-10, reason).

    Why this exists: nothing human sees these images before they go public, five
    times a day. The pixel gate in passes_quality_gate() can only measure
    brightness and variance — it cannot tell you the subject has three hands, that
    the model scribbled fake lettering across the wall, or that the frame contains
    no person at all. Those are the failures that actually embarrass a channel,
    and they are invisible to statistics but obvious to anything that can see.

    On failure to reach the model it returns a neutral pass (5) rather than
    blocking: an outage should not stop the post, it should just stop the extra
    scrutiny. Score 5 still loses to any candidate that scored higher.
    """
    if not VISION_GATE_ENABLED:
        return 5, "vision gate disabled"
    if not OPENROUTER_API_KEY:
        return 5, "no API key for vision gate"

    payload = {
        "model": VISION_MODEL,
        "max_tokens": 100,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_RUBRIC},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{_encode_jpeg(img)}"
                }},
            ],
        }],
    }
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            timeout=90,
        )
        if resp.status_code >= 400:
            print(f"    vision gate HTTP {resp.status_code}: {resp.text[:200]}")
            return 5, "vision gate unavailable"
        text = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"    vision gate failed ({type(e).__name__}) — not blocking")
        return 5, "vision gate errored"

    score, reason = 5, text.strip()[:120]
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            digits = "".join(c for c in line.split(":", 1)[1] if c.isdigit())
            if digits:
                score = max(0, min(10, int(digits[:2])))
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()[:120]
    return score, reason


def generate_background(quote: str, theme: str, attempts: int = 2) -> dict | None:
    """Generate a background for this quote.

    Returns {path, prompt, subject, model, provider} on success, None on failure.
    None is a normal outcome, not an error: the caller falls back to the existing
    black card, so a bad generation costs a plainer post rather than a lost slot.
    """
    if IMAGE_PROVIDER != "openrouter":
        print(f"    unknown IMAGE_PROVIDER: {IMAGE_PROVIDER}")
        return None

    subject = _subject_brief(quote, theme)
    prompt = build_prompt(subject)
    print(f"  Subject: {subject}")

    # Two filters in series, cheapest first. The pixel gate is free and catches
    # unreadable frames; the vision gate costs a call and catches wrong ones.
    # Best-of-N rather than first-acceptable: with several candidates in hand,
    # picking the highest-scoring one is strictly better than taking whichever
    # happened to come back first.
    candidates = _generate_openrouter(prompt, n=IMAGE_CANDIDATES)
    if not candidates:
        print("  No usable background — falling back to plain card")
        return None

    scored = []
    for i, img in enumerate(candidates):
        framed = _crop_to_frame(img)
        ok, reason = passes_quality_gate(framed)
        if not ok:
            print(f"    candidate {i + 1}: rejected — {reason}")
            continue
        score, why = vision_score(framed)
        print(f"    candidate {i + 1}: {score}/10 — {why}")
        if score >= VISION_MIN_SCORE:
            scored.append((score, why, framed))

    if not scored:
        print("  No candidate passed the gates — falling back to plain card")
        return None

    score, why, framed = max(scored, key=lambda s: s[0])
    path = IMAGES_DIR / f"bg_{int(time.time())}.jpg"
    framed.save(path, "JPEG", quality=92)
    print(f"  Background: {path.name} (score {score}/10)")
    return {
        "path": path,
        "prompt": prompt,
        "subject": subject,
        "model": IMAGE_MODEL,
        "provider": IMAGE_PROVIDER,
        "vision_score": score,
        "vision_reason": why,
    }


def verify_image_engine() -> bool:
    """One-shot check: generate frames, run both gates, report exactly what broke."""
    print(f"Provider     : {IMAGE_PROVIDER}")
    print(f"Image model  : {IMAGE_MODEL}")
    print(f"Vision model : {VISION_MODEL} ({'on' if VISION_GATE_ENABLED else 'OFF'})")
    print(f"Candidates   : {IMAGE_CANDIDATES}")
    print(f"API key      : {'set' if OPENROUTER_API_KEY else 'MISSING'}")
    if not OPENROUTER_API_KEY:
        print("\nSet OPENROUTER_API_KEY in .env.")
        return False

    subject = THEME_SUBJECTS["discipline"]
    prompt = build_prompt(subject)
    print(f"\nPrompt:\n  {prompt}\n")

    images = _generate_openrouter(prompt, n=IMAGE_CANDIDATES)
    if not images:
        print("FAILED — see the error above.")
        print("If it names a parameter, edit the `payload` dict in _generate_openrouter.")
        return False

    any_pass = False
    for i, img in enumerate(images):
        framed = _crop_to_frame(img)
        ok, reason = passes_quality_gate(framed)
        score, why = vision_score(framed) if ok else (0, "skipped, failed pixel gate")
        out = IMAGES_DIR / f"verify_background_{i + 1}.jpg"
        framed.save(out, "JPEG", quality=92)
        verdict = "PASS" if (ok and score >= VISION_MIN_SCORE) else "REJECT"
        any_pass = any_pass or verdict == "PASS"
        print(f"candidate {i + 1}: {img.size[0]}x{img.size[1]} -> {WIDTH}x{HEIGHT}")
        print(f"  pixel gate : {'ok' if ok else 'FAIL — ' + reason}")
        print(f"  vision gate: {score}/10 — {why}")
        print(f"  verdict    : {verdict}")
        print(f'  open "{out}"')

    print("\nLook at the images before enabling — the gates catch broken, not bland.")
    return any_pass
