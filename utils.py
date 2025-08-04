# utils.py

import os
import json
import random
import requests
import time
import tweepy
from datetime import datetime

# ─────────── CONFIG ───────────
USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
QUEUE_FILE         = "/data/queue.json"
B2_IMAGE_BASE_URL  = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE    = "/tmp/temp_image.png"  # scratch download

# ────────── STORAGE HELPERS ──────────
def _load_set(path):
    if os.path.exists(path):
        return set(json.load(open(path)))
    return set()

def _save_set(s, path):
    with open(path, "w") as f:
        json.dump(list(s), f)

def _load_json(path, default):
    if os.path.exists(path):
        return json.load(open(path))
    return default

def _save_json(o, path):
    with open(path, "w") as f:
        json.dump(o, f)

def load_queue():
    return _load_json(QUEUE_FILE, [])

def save_queue(q):
    _save_json(q, QUEUE_FILE)

# ───────── DOWNLOAD IMAGE ─────────
def _download_image(filename):
    url = B2_IMAGE_BASE_URL + filename
    try:
        r = requests.get(url); r.raise_for_status()
        with open(TEMP_IMAGE_FILE, "wb") as f:
            f.write(r.content)
        return TEMP_IMAGE_FILE
    except Exception as e:
        print(f"❌ download failed: {e}")
        return None

# ───────── PHASE 1: BATCH ENQUEUE ─────────
def batch_enqueue(client_v2):
    state      = _load_json(STATE_FILE, {"last_seen_id": None})
    last_seen  = state["last_seen_id"]
    queue      = load_queue()
    queued_ids = {job["tweet_id"] for job in queue}
    recipients = _load_set(RECIPIENTS_FILE)

    print(f"[{datetime.utcnow()}] 🔍 batch_enqueue: since_id={last_seen}")
    try:
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me -is:retweet",
            since_id=last_seen,
            max_results=100,
            expansions=["author_id"],
            user_fields=["username"]
        )
    except Exception as e:
        print(f"❌ search_recent_tweets failed: {e}")
        return

    tweets = resp.data or []
    users  = {u["id"]: u["username"].lower() for u in resp.includes.get("users", [])}

    new_last = last_seen
    for tw in reversed(tweets):
        tid = tw.id
        if not new_last or tid > new_last:
            new_last = tid
        if tid in queued_ids:
            continue
        if "create a pfp for me" not in tw.text.lower():
            continue
        usr = users.get(tw.author_id)
        if not usr or usr in recipients:
            continue
        queue.append({"tweet_id": tid, "screen_name": usr})
        print(f"➕ queued @{usr} (tweet {tid})")

    if new_last and new_last != last_seen:
        state["last_seen_id"] = new_last
        _save_json(state, STATE_FILE)
    save_queue(queue)

# ───────── PHASE 2: DRIP REPLY ─────────
def drip_reply(client_v1, client_v2=None):
    queue      = load_queue()
    if not queue:
        return

    used       = _load_set(USED_IMAGES_FILE)
    recipients = _load_set(RECIPIENTS_FILE)
    job        = queue.pop(0)
    tid        = job["tweet_id"]
    usr        = job["screen_name"]

    # double-check
    if usr in recipients or usr in used:
        save_queue(queue)
        return

    # pick & download image
    all_imgs  = [f"{i}.png" for i in range(10000)]
    avail     = list(set(all_imgs) - used)
    if not avail:
        print("⚠️  no images left")
        return
    img_file = random.choice(avail)
    img_path = _download_image(img_file)
    if not img_path:
        print(f"⚠️ download failed, requeueing @{usr}")
        queue.insert(0, job); save_queue(queue)
        return

    # upload media
    try:
        print(f"📤 uploading {img_file}")
        media = client_v1.media_upload(img_path)
    except Exception as e:
        print(f"❌ media_upload failed: {e}")
        queue.insert(0, job); save_queue(queue)
        return
    finally:
        os.remove(img_path)

    # craft a random reply
    templates = [
        "Here's your Nobody PFP 👁️ @{u}",
        "Your custom Nobody PFP is ready 👁️ @{u}",
        "All yours 👁️ @{u}",
        "Cooked just for you 👁️ @{u}",
        "Made with nothingness 👁️ @{u}",
        "👁️ For the void... @{u}",
    ]
    status = random.choice(templates).replace("{u}", usr)

    # post reply
    try:
        print(f"📢 replying to @{usr} (tweet {tid})")
        client_v1.update_status(
            status=status,
            in_reply_to_status_id=tid,
            auto_populate_reply_metadata=True,
            media_ids=[media.media_id_string]
        )
    except tweepy.TooManyRequests as e:
        reset_ts = int(e.response.headers.get("x-rate-limit-reset", time.time()+60))
        now_ts   = int(time.time())
        wait_s   = max(reset_ts - now_ts + 5, 10)
        print(f"🚫 rate limit—requeueing, sleeping {wait_s}s")
        queue.insert(0, job); save_queue(queue)
        time.sleep(wait_s)
        return
    except Exception as e:
        print(f"❌ update_status failed: {e}")
        # don’t retry permanent errors
        return

    # success → record
    used.add(img_file)
    recipients.add(usr)
    _save_set(used, USED_IMAGES_FILE)
    _save_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)
    print(f"✅ done @{usr}")
