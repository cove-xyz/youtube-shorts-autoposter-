"""Simple Flask server to serve images for Meta API (needs public URLs)."""
from flask import Flask, send_from_directory, jsonify
from src.config import IMAGES_DIR
from src.database import init_db, get_all_queued, get_posted_posts, get_queue_count

app = Flask(__name__)


@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(str(IMAGES_DIR), filename)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/status")
def status():
    init_db()
    return jsonify({
        "feed_queue": get_queue_count("feed"),
        "story_queue": get_queue_count("story"),
        "recent_posts": len(get_posted_posts(days=1)),
        "queued_items": len(get_all_queued()),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
