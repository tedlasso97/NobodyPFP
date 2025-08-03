# utils.py
import os
import json
import random
import requests
import time

# ─── Config ───────────────────────────────────────────────────────────────────
USED_IMAGES_FILE  = "/data/used_images.json"
RECIPIENTS_FILE   = "/data/recipients.json"
STATE_FILE        = "/data/state.json"
FAILED_FILE       = "/data/failed.json"
QUEUE_FILE        = "/data/queue.json"
B2_IMAGE_BASE_URL = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE   = "temp_image.png"

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _load_set(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return set(json.load(f))
    return set()

def _save_set(s, path):
    with open(path, "w") as f:
        json.dump(list(s), f)

def _load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def _save_json(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f)

# ─── Queue & State ────────────────────────────────────────────────────────────
def load_queue():
    return _load_json(QUEUE_FILE, [])

def save_queue(q):
    _save_json(q, QUEUE_FILE)

def load_state():
    return _load_json(STATE_FILE, {"last_seen_id": None})

def save_state(s):
    _save_json(s, STATE_FILE)

# ─── Image download ───────────────────────────────────────────────────────────
def _download_image(filename):
    url = f"{B2_IMAGE_BASE_URL}{filename}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        with open(TEMP_IMAGE_FILE, "wb") as f:
            f.write(resp.content)
        return TEMP_IMAGE_FILE
    except Exception as e:
        print(f"❌ Image download failed: {e}")
        return None

def _pick_image(used_set):
    # assume images are named 0.png … 9999.png
    all_imgs = {f"{i}.png" for i in range(10_000)}
    avail = list(all_imgs - used_set)
    return random.choice(avail) if avail else None

# ─── Fetch mentions & enqueue ─────────────────────────────────────────────────
def respond_to_mentions(client_v2, *, batch_size=10):
    recipients = _load_set(RECIPIENTS_FILE)
    failed     = _load_set(FAILED_FILE)
    state      = load_state()
    queue      = load_queue()

    last_seen = state.get("last_seen_id")
    try:
        print("🔍 Searching for new mentions…")
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me -is:retweet",
            since_id=last_seen,
            max_results=batch_size,
            tweet_fields=["author_id"]
        )
        tweets = resp.data or []
        print(f"✅ Found {len(tweets)} tweets")
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return

    new_last = last_seen or 0
    queued_ids = {job["tweet_id"] for job in queue}

    for tw in reversed(tweets):
        tid  = tw.id
        text = tw.text.lower()
        if tid > new_last:
            new_last = tid
        if "create a pfp for me" not in text:
            continue

        # look up username
        try:
            user = client_v2.get_user(id=tw.author_id).data.username.lower()
        except Exception as e:
            print(f"❌ User lookup failed: {e}")
            continue

        if tid in queued_ids or user in recipients or user in failed:
            continue

        queue.append({"tweet_id": tid, "screen_name": user})
        print(f"➕ Queued @{user} (tweet {tid})")

    if new_last:
        state["last_seen_id"] = new_last
        save_state(state)
    save_queue(queue)

# ─── Serve queued replies ──────────────────────────────────────────────────────
def serve_from_queue(client_v2, reply_interval_sec=300):
    queue      = load_queue()
    if not queue:
        print("📋 Queue empty")
        return

    used       = _load_set(USED_IMAGES_FILE)
    recipients = _load_set(RECIPIENTS_FILE)
    failed     = _load_set(FAILED_FILE)

    job = queue.pop(0)
    tid  = job["tweet_id"]
    usr  = job["screen_name"]

    # skip if already done
    if usr in recipients or usr in failed:
        save_queue(queue)
        return

    img_name = _pick_image(used)
    if not img_name:
        print("⚠️ No images left")
        return

    path = _download_image(img_name)
    if not path:
        failed.add(usr)
        _save_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    # 1) upload via v2
    try:
        print(f"📤 Uploading {img_name}…")
        media = client_v2.upload_media(filename=path)
        media_key = media.media_key
    except Exception as e:
        print(f"❌ Media upload failed: {e}")
        failed.add(usr)
        _save_set(failed, FAILED_FILE)
        save_queue(queue)
        return
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)

    # 2) create tweet
    templates = [
        "Here's your Nobody PFP 👁️ @{screen_name}",
        "Your custom Nobody PFP is ready 👁️ @{screen_name}",
        "All yours 👁️ @{screen_name}",
        "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
        "Cooked just for you 👁️ @{screen_name}",
        "Made with nothingness 👁️ @{screen_name}",
        "👁️ For the void... and @{screen_name}",
    ]
    text = random.choice(templates).format(screen_name=usr)

    try:
        print(f"📢 Replying to @{usr}…")
        client_v2.create_tweet(
            text=text,
            in_reply_to_tweet_id=tid,
            media_ids=[media_key]
        )
        print(f"✅ Sent {img_name} to @{usr}")
    except Exception as e:
        print(f"❌ Reply failed: {e}")
        # rate‐limit → re‐queue and back off
        if "429" in str(e):
            queue.insert(0, job)
            print("🚫 Rate limit, re-queued and sleeping 60s…")
            time.sleep(60)
        failed.add(usr)
        _save_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    # record success
    used.add(img_name)
    recipients.add(usr)
    _save_set(used, USED_IMAGES_FILE)
    _save_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)

    # throttle
    time.sleep(reply_interval_sec)
