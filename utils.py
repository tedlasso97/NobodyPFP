import os
import json
import random
import requests
import time

# ─── CONFIG ───────────────────────────────────────────────────────────────────
USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
FAILED_FILE        = "/data/failed.json"
QUEUE_FILE         = "/data/queue.json"

B2_IMAGE_BASE_URL  = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE    = "temp_image.png"

# ─── HELPERS ──────────────────────────────────────────────────────────────────
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

# ─── IMAGE FUNCTIONS ──────────────────────────────────────────────────────────
def get_unused_image(used_images):
    all_imgs = [f"{i}.png" for i in range(10000)]
    avail    = list(set(all_imgs) - used_images)
    return random.choice(avail) if avail else None

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

# ─── QUEUE BUILDER ────────────────────────────────────────────────────────────
def respond_to_mentions(client_v2, client_v1):
    recipients   = load_json_set(RECIPIENTS_FILE)
    failed       = load_json_set(FAILED_FILE)
    state        = load_state()
    last_seen    = state.get("last_seen_id")
    queue        = load_queue()

    print("🔍 Searching for new mentions…")
    try:
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me -is:retweet",
            since_id=last_seen,
            max_results=10,
            tweet_fields=["author_id"]
        )
        tweets = resp.data or []
        print("✅ Found tweets:", [t.id for t in tweets])
    except Exception as e:
        print(f"❌ Error searching tweets: {e}")
        return

    new_last = last_seen
    queued   = {job["tweet_id"] for job in queue}

    for tw in reversed(tweets):
        tid  = tw.id
        txt  = tw.text.lower()
        if tid > (new_last or 0):
            new_last = tid
        if "create a pfp for me" not in txt:
            continue

        # fetch username
        try:
            usr = client_v2.get_user(id=tw.author_id).data.username.lower()
        except Exception as e:
            print(f"❌ Error fetching user: {e}")
            continue

        if tid in queued or usr in recipients or usr in failed:
            continue

        queue.append({"tweet_id": tid, "screen_name": usr})
        print(f"➕ Queued @{usr} (tweet {tid})")

    if new_last:
        state["last_seen_id"] = new_last
        save_state(state)
    save_queue(queue)

# ─── QUEUE CONSUMER ────────────────────────────────────────────────────────────
def serve_from_queue(client_v1):
    queue       = load_queue()
    if not queue:
        print("📋 Queue empty.")
        return

    used_imgs   = load_json_set(USED_IMAGES_FILE)
    recipients  = load_json_set(RECIPIENTS_FILE)
    failed      = load_json_set(FAILED_FILE)

    job         = queue.pop(0)
    tid         = job["tweet_id"]
    usr         = job["screen_name"]

    # skip if already done
    if usr in recipients or usr in failed:
        save_queue(queue)
        return

    img_fn      = get_unused_image(used_imgs)
    if not img_fn:
        print("⚠️ No unused images left.")
        return

    img_path    = download_image(img_fn)
    if not img_path:
        print(f"⚠️ Download failed, marking @{usr} failed.")
        failed.add(usr); save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    # upload media
    try:
        print(f"📤 Uploading {img_fn}…")
        media = client_v1.media_upload(img_path)
    except Exception as e:
        print(f"❌ Media upload failed: {e}")
        failed.add(usr); save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)

    # post reply via v1.1
    reply_text = f"Here is your Nobody PFP @{usr}"
    try:
        print(f"📢 Replying to @{usr} (tweet {tid})…")
        client_v1.update_status(
            status=reply_text,
            in_reply_to_status_id=tid,
            auto_populate_reply_metadata=True,
            media_ids=[media.media_id_string]
        )
        print(f"🎉 Sent {img_fn} to @{usr}")
    except Exception as e:
        print(f"❌ Reply failed: {e}")
        failed.add(usr); save_json_set(failed, FAILED_FILE)

        if "429" in str(e):
            print("🚫 Rate limit – re-queueing & sleeping 300s…")
            queue.insert(0, job); save_queue(queue); time.sleep(300)
        return

    # record success
    used_imgs.add(img_fn); save_json_set(used_imgs, USED_IMAGES_FILE)
    recipients.add(usr);  save_json_set(recipients,  RECIPIENTS_FILE)
    save_queue(queue)

    # small throttle
    time.sleep(10)
