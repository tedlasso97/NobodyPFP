import os
import json
import random
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────────
USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
FAILED_FILE        = "/data/failed.json"
QUEUE_FILE         = "/data/queue.json"
B2_IMAGE_BASE_URL  = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE    = "temp_image.png"

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def load_json_set(path):
    try:
        with open(path, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_json_set(data_set, path):
    with open(path, "w") as f:
        json.dump(list(data_set), f)

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {"last_seen_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_queue():
    try:
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f)

# ─── IMAGE FUNCTIONS ───────────────────────────────────────────────────────────
def get_unused_image(used_images):
    all_images = [f"{i}.png" for i in range(10000)]
    available  = list(set(all_images) - used_images)
    return random.choice(available) if available else None

def download_image(filename):
    url = f"{B2_IMAGE_BASE_URL}{filename}"
    try:
        r = requests.get(url)
        r.raise_for_status()
        with open(TEMP_IMAGE_FILE, "wb") as out:
            out.write(r.content)
        return TEMP_IMAGE_FILE
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        return None

# ─── QUEUE BUILDER ─────────────────────────────────────────────────────────────
def respond_to_mentions(client_v2):
    """
    Fetch new mentions (excluding retweets) via v2,
    skip users already served or failed, enqueue for reply.
    """
    recipients   = load_json_set(RECIPIENTS_FILE)
    failed       = load_json_set(FAILED_FILE)
    state        = load_state()
    last_seen_id = state.get("last_seen_id")
    queue        = load_queue()

    try:
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me -is:retweet",
            since_id=last_seen_id,
            max_results=10,
            tweet_fields=["author_id"]
        )
        tweets = resp.data or []
        print("✅ Found tweets:", tweets)
    except Exception as e:
        print(f"❌ Error fetching mentions: {e}")
        return

    new_last = last_seen_id
    existing = {job["tweet_id"] for job in queue}

    for tw in reversed(tweets):
        tid = tw.id
        if new_last is None or tid > new_last:
            new_last = tid

        if "create a pfp for me" not in tw.text.lower():
            continue

        # lookup screen_name
        try:
            user = client_v2.get_user(id=tw.author_id).data.username.lower()
        except Exception as e:
            print(f"❌ Error fetching user: {e}")
            continue

        if tid in existing or user in recipients or user in failed:
            continue

        queue.append({"tweet_id": tid, "screen_name": user})
        print(f"➕ Queued @{user} (tweet {tid})")

    if new_last:
        state["last_seen_id"] = new_last
        save_state(state)
    save_queue(queue)

# ─── QUEUE CONSUMER ────────────────────────────────────────────────────────────
def serve_from_queue(client_v1):
    """
    Pop one job, upload image + reply via v1.1.
    On 429, re-queue immediately (no sleep), let scheduler retry later.
    """
    queue        = load_queue()
    if not queue:
        return

    used_images  = load_json_set(USED_IMAGES_FILE)
    recipients   = load_json_set(RECIPIENTS_FILE)
    failed       = load_json_set(FAILED_FILE)
    job          = queue.pop(0)
    tid          = job["tweet_id"]
    user         = job["screen_name"]

    # skip duplicates
    if user in recipients or user in failed:
        save_queue(queue)
        return

    img_file = get_unused_image(used_images)
    if not img_file:
        print("⚠️ No unused images left.")
        save_queue(queue)
        return

    img_path = download_image(img_file)
    if not img_path:
        print(f"⚠️ Download failed for {img_file}, marking failed.")
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    # upload media
    try:
        print(f"📤 Uploading media {img_file}…")
        media = client_v1.media_upload(img_path)
    except Exception as e:
        print(f"❌ Media upload failed: {e}")
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        queue.insert(0, job)
        save_queue(queue)
        return
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)

    # craft reply
    templates = [
        "Here's your Nobody PFP 👁️ @{screen_name}",
        "Your custom Nobody PFP is ready 👁️ @{screen_name}",
        "All yours 👁️ @{screen_name}",
        "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
        "Cooked just for you 👁️ @{screen_name}",
        "Made with nothingness 👁️ @{screen_name}",
        "👁️ For the void... and @{screen_name}",
    ]
    status = random.choice(templates).format(screen_name=user)

    # post reply
    try:
        print(f"📢 Replying to @{user}…")
        client_v1.update_status(
            status=status,
            in_reply_to_status_id=tid,
            auto_populate_reply_metadata=True,
            media_ids=[media.media_id_string]
        )
        print(f"🎉 Sent PFP {img_file} to @{user}")
    except Exception as e:
        print(f"❌ Reply failed: {e}")
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        # on rate-limit, re-queue and bail
        if "429" in str(e):
            print("🚫 Rate limit — re-queueing.")
            queue.insert(0, job)
            save_queue(queue)
        return

    # record success
    used_images.add(img_file)
    recipients.add(user)
    save_json_set(used_images, USED_IMAGES_FILE)
    save_json_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)
