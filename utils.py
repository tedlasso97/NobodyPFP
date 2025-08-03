import os
import json
import random
import requests
import time
import datetime

USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
FAILED_FILE        = "/data/failed.json"
QUEUE_FILE         = "/data/queue.json"

B2_IMAGE_BASE_URL  = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE    = "temp_image.png"

# ————————————————
# Load/save helpers
# ————————————————
def load_json_set(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return set(json.load(f))
    return set()

def save_json_set(data_set, path):
    with open(path, "w") as f:
        json.dump(list(data_set), f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_seen_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ————————————————
# Image picker & downloader
# ————————————————
def get_unused_image(used_images):
    all_images = [f"{i}.png" for i in range(0, 10000)]
    available  = list(set(all_images) - used_images)
    return random.choice(available) if available else None

def download_image(image_filename):
    url = f"{B2_IMAGE_BASE_URL}{image_filename}"
    try:
        r = requests.get(url); r.raise_for_status()
        with open(TEMP_IMAGE_FILE, "wb") as f:
            f.write(r.content)
        return TEMP_IMAGE_FILE
    except Exception as e:
        print(f"❌ Error downloading image: {e}")
        return None

# ————————————————
# Queue loading & saving
# ————————————————
def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    return []

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f)

# ————————————————
# Fetch mentions → build work queue
# ————————————————
def respond_to_mentions(client_v2, client_v1):
    recipients    = load_json_set(RECIPIENTS_FILE)
    failed        = load_json_set(FAILED_FILE)
    state         = load_state()
    last_seen_id  = state.get("last_seen_id")
    queue         = load_queue()

    try:
        print("🔍 Searching for new mentions…")
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me",
            since_id=last_seen_id,
            max_results=10,
            tweet_fields=["author_id"]
        )
        tweets = resp.data or []
        print("✅ Found tweets:", tweets)
    except Exception as e:
        print("❌ Error searching tweets:", e)
        return

    new_last_seen = last_seen_id
    queued_ids    = {item["tweet_id"] for item in queue}

    for tw in reversed(tweets):
        tid  = tw.id
        txt  = tw.text.lower()
        if tid > (new_last_seen or 0):
            new_last_seen = tid
        if "create a pfp for me" not in txt:
            continue

        try:
            user_obj    = client_v2.get_user(id=tw.author_id)
            screen_name = user_obj.data.username.lower()
        except Exception as e:
            print("❌ Error fetching user:", e)
            continue

        if tid in queued_ids or screen_name in recipients or screen_name in failed:
            continue

        queue.append({
            "tweet_id":   tid,
            "author_id":  tw.author_id,
            "screen_name": screen_name
        })

    if new_last_seen:
        state["last_seen_id"] = new_last_seen
        save_state(state)
    save_queue(queue)

# ————————————————
# Serve replies from queue
# ————————————————
def serve_from_queue(client_v1, client_v2):
    queue       = load_queue()
    used_images = load_json_set(USED_IMAGES_FILE)
    recipients  = load_json_set(RECIPIENTS_FILE)
    failed      = load_json_set(FAILED_FILE)

    print(f"📋 Queue length: {len(queue)}")
    if not queue:
        return

    job = queue.pop(0)
    tid  = job["tweet_id"]
    user = job["screen_name"]

    if user in recipients or user in failed:
        save_queue(queue); return

    img_file = get_unused_image(used_images)
    if not img_file:
        print("⚠️ No more unused images."); return

    img_path = download_image(img_file)
    if not img_path:
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    # 1️⃣ Upload media via v1.1
    try:
        print("📤 Uploading media…")
        media = client_v1.media_upload(img_path)
    except Exception as e:
        print("❌ Media upload failed:", e)
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)

    # 2️⃣ Post reply via v2
    responses = [
        "Here's your Nobody PFP 👁️ @{screen_name}",
        "Your custom Nobody PFP is ready 👁️ @{screen_name}",
        "All yours 👁️ @{screen_name}",
        "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
        "Cooked just for you 👁️ @{screen_name}",
        "Made with nothingness 👁️ @{screen_name}",
        "👁️ For the void... and @{screen_name}",
    ]
    status_text = random.choice(responses).replace("{screen_name}", user)

    try:
        print("📢 Posting reply via v2…")
        client_v2.create_tweet(
            text=status_text,
            in_reply_to_tweet_id=tid,
            media_ids=[media.media_id_string]
        )
        print(f"🎉 Sent PFP {img_file} to @{user}")
    except Exception as e:
        print("❌ Post failed:", e)
        failed.add(user)
        save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    used_images.add(img_file)
    recipients.add(user)
    save_json_set(used_images, USED_IMAGES_FILE)
    save_json_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)

    # small delay to stay under rate limits
    time.sleep(10)
