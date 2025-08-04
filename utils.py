import os
import json
import random
import requests
import time
import tweepy
from datetime import datetime

# ─── Paths ─────────────────────────────────────────────────────────────────────
USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
FAILED_FILE        = "/data/failed.json"
QUEUE_FILE         = "/data/queue.json"
B2_IMAGE_BASE_URL  = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE    = "temp_image.png"

# ─── Helpers ───────────────────────────────────────────────────────────────────
def load_json_set(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return set(json.load(f))
    return set()

def save_json_set(data, path):
    with open(path, "w") as f:
        json.dump(list(data), f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_seen_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    return []

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f)

# ─── Image ─────────────────────────────────────────────────────────────────────
def get_unused_image(used_images):
    all_imgs = [f"{i}.png" for i in range(10000)]
    choices = list(set(all_imgs) - used_images)
    return random.choice(choices) if choices else None

def download_image(fn):
    url = f"{B2_IMAGE_BASE_URL}{fn}"
    try:
        r = requests.get(url); r.raise_for_status()
        with open(TEMP_IMAGE_FILE, "wb") as f:
            f.write(r.content)
        return TEMP_IMAGE_FILE
    except Exception as e:
        print(f"❌ Error downloading {fn}: {e}")
        return None

# ─── Phase 1: batch_enqueue ────────────────────────────────────────────────────
def batch_enqueue(client_v2):
    recipients   = load_json_set(RECIPIENTS_FILE)
    failed       = load_json_set(FAILED_FILE)
    state        = load_state()
    last_seen    = state.get("last_seen_id")
    queue        = load_queue()

    try:
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me -is:retweet",
            since_id=last_seen,
            max_results=50,
            tweet_fields=["author_id"]
        )
        tweets = resp.data or []
    except Exception as e:
        print(f"❌ batch_enqueue search error: {e}")
        return

    new_last = last_seen
    queued_ids = {j["tweet_id"] for j in queue}

    for tw in reversed(tweets):
        if tw.id > (new_last or 0):
            new_last = tw.id
        if "create a pfp for me" not in tw.text.lower():
            continue
        try:
            user = client_v2.get_user(id=tw.author_id).data.username.lower()
        except Exception as e:
            print(f"❌ batch_enqueue user lookup: {e}")
            continue
        if tw.id in queued_ids or user in recipients or user in failed:
            continue

        queue.append({"tweet_id": tw.id, "screen_name": user})
        print(f"➕ Queued @{user} for tweet {tw.id}")

    if new_last and new_last != last_seen:
        state["last_seen_id"] = new_last
        save_state(state)
    save_queue(queue)

# ─── Phase 2: drip_reply ───────────────────────────────────────────────────────
def drip_reply(client_v1):
    queue      = load_queue()
    if not queue:
        print("ℹ️ Queue empty.")
        return

    used       = load_json_set(USED_IMAGES_FILE)
    recipients = load_json_set(RECIPIENTS_FILE)
    failed     = load_json_set(FAILED_FILE)
    job        = queue.pop(0)
    save_queue(queue)

    tid        = job["tweet_id"]
    user       = job["screen_name"]

    if user in recipients or user in failed:
        print(f"⚠️ Skip @{user} (already handled).")
        return

    img = get_unused_image(used)
    if not img:
        print("⚠️ No images left.")
        return

    path = download_image(img)
    if not path:
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        return

    # upload media
    try:
        print(f"📤 Uploading {img}…")
        media = client_v1.media_upload(path)
    except Exception as e:
        print(f"❌ Media upload failed: {e}")
        failed.add(user); save_json_set(failed, FAILED_FILE)
        return
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)

    # randomized reply text
    templates = [
        "Here's your Nobody PFP 👁️ @{screen_name}",
        "Your custom Nobody PFP is ready 👁️ @{screen_name}",
        "All yours 👁️ @{screen_name}",
        "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
        "Cooked just for you 👁️ @{screen_name}",
        "Made with nothingness 👁️ @{screen_name}",
        "👁️ For the void... and @{screen_name}",
    ]
    text = random.choice(templates).format(screen_name=user)

    # post reply
    try:
        print(f"📢 Replying to @{user}…")
        client_v1.update_status(
            status=text,
            in_reply_to_status_id=tid,
            auto_populate_reply_metadata=True,
            media_ids=[media.media_id_string]
        )
        print(f"✅ Sent PFP {img} to @{user}")
    except tweepy.errors.TooManyRequests as e:
        reset_ts = int(e.response.headers.get("x-rate-limit-reset", time.time()+60))
        wait     = max(reset_ts - time.time(), 10)
        print(f"🚫 Rate limit – sleeping {int(wait)}s until reset…")
        queue.insert(0, job)
        save_queue(queue)
        time.sleep(wait)
        return
    except Exception as e:
        print(f"❌ Reply failed: {e}")
        failed.add(user); save_json_set(failed, FAILED_FILE)
        return

    # record success
    used.add(img);       save_json_set(used, USED_IMAGES_FILE)
    recipients.add(user);save_json_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)

    # light throttle
    time.sleep(5)
