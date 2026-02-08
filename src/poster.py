"""Core posting pipeline - generates content, creates images, and posts."""
from src.config import BASE_URL
from src.content_generator import generate_content
from src.image_generator import generate_feed_image, generate_story_image
from src.caption_generator import generate_caption, generate_story_caption
from src.safety_filter import is_safe, filter_caption
from src.instagram_api import publish_feed_post, publish_story
from src.database import queue_post, get_next_post, mark_posted, mark_failed, get_queue_count


def create_feed_content() -> dict | None:
    """Generate and queue a feed post."""
    content = generate_content(post_type="feed")
    if not content:
        print("[WARN] Failed to generate content")
        return None

    # Safety check
    safe, reason = is_safe(content["text"])
    if not safe:
        print(f"[FILTERED] {reason}: {content['text'][:60]}...")
        return None

    # Generate image
    image_path = generate_feed_image(content["text"])

    # Generate caption
    caption = generate_caption(content["text"], content["theme"])
    cap_safe, cap_reason = filter_caption(caption)
    if not cap_safe:
        print(f"[FILTERED] Caption: {cap_reason}")
        return None

    # Queue it
    post_id = queue_post(
        content_text=content["text"],
        caption=caption,
        image_path=str(image_path),
        post_type="feed",
        theme=content["theme"],
    )

    print(f"[QUEUED] Feed post #{post_id}: {content['text'][:60]}...")
    return {"id": post_id, "text": content["text"], "image": str(image_path)}


def create_story_content() -> dict | None:
    """Generate and queue a story post."""
    content = generate_content(post_type="story")
    if not content:
        print("[WARN] Failed to generate story content")
        return None

    safe, reason = is_safe(content["text"])
    if not safe:
        print(f"[FILTERED] {reason}: {content['text'][:60]}...")
        return None

    image_path = generate_story_image(content["text"])

    post_id = queue_post(
        content_text=content["text"],
        caption="",
        image_path=str(image_path),
        post_type="story",
        theme=content["theme"],
    )

    print(f"[QUEUED] Story #{post_id}: {content['text'][:60]}...")
    return {"id": post_id, "text": content["text"], "image": str(image_path)}


def post_next_feed():
    """Post the next queued feed item to Instagram."""
    post = get_next_post("feed")
    if not post:
        print("[INFO] No feed posts in queue, generating...")
        result = create_feed_content()
        if not result:
            print("[ERROR] Could not create feed content")
            return
        post = get_next_post("feed")
        if not post:
            return

    image_url = f"{BASE_URL}/images/{post['image_path'].split('/')[-1]}"
    media_id = publish_feed_post(image_url, post.get("caption", ""))

    if media_id:
        mark_posted(post["id"], media_id)
        print(f"[POSTED] Feed #{post['id']}")
    else:
        mark_failed(post["id"])
        print(f"[FAILED] Feed #{post['id']}")


def post_next_story():
    """Post the next queued story to Instagram."""
    post = get_next_post("story")
    if not post:
        print("[INFO] No stories in queue, generating...")
        result = create_story_content()
        if not result:
            print("[ERROR] Could not create story content")
            return
        post = get_next_post("story")
        if not post:
            return

    image_url = f"{BASE_URL}/images/{post['image_path'].split('/')[-1]}"
    media_id = publish_story(image_url)

    if media_id:
        mark_posted(post["id"], media_id)
        print(f"[POSTED] Story #{post['id']}")
    else:
        mark_failed(post["id"])
        print(f"[FAILED] Story #{post['id']}")


def ensure_queue(feed_min: int = 6, story_min: int = 10):
    """Make sure there are enough posts queued up."""
    feed_count = get_queue_count("feed")
    story_count = get_queue_count("story")

    print(f"[QUEUE] Feed: {feed_count} | Stories: {story_count}")

    while feed_count < feed_min:
        result = create_feed_content()
        if result:
            feed_count += 1
        else:
            break

    while story_count < story_min:
        result = create_story_content()
        if result:
            story_count += 1
        else:
            break

    print(f"[QUEUE] After refill - Feed: {feed_count} | Stories: {story_count}")
