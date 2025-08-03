import os
import json
import random
import requests
import time
import datetime

USED_IMAGES_FILE = "/data/used_images.json"
RECIPIENTS_FILE = "/data/recipients.json"
STATE_FILE = "/data/state.json"
FAILED_FILE = "/data/failed.json"
QUEUE_FILE = "/data/queue.json"

B2_IMAGE_BASE_URL = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE = "temp_image.png"

# Load/save helpers
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

# Image picker and downloader
def get_unused_image(used_images):
    all_images = [f"{i}.png" for i in range(0, 10000)]
    available = list(set(all_images) - used_images)
    if not available:
        return None
    return random.choice(available)

def download_image(image_filename):
    url = f"{B2_IMAGE_BASE_URL}{image_filename}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(TEMP_IMAGE_FILE, "wb") as f:
            f.write(response.content)
        return TEMP_IMAGE_FILE
    except Exception as e:
        print(f"Error downloading image from B2: {e}")
        return None

# Queue loading and saving
def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    return []

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f)

def has_recent_reply(client_v1, screen_name):
    try:
        replies = client_v1.user_timeline(count=50, tweet_mode="extended")
        now = datetime.datetime.utcnow()
        for tweet in replies:
            if tweet.in_reply_to_screen_name and screen_name.lower() in tweet.full_text.lower():
                created_at = tweet.created_at
                age = (now - created_at).total_seconds()
                if age <= 6 * 3600:
                    print(f"🕒 Found recent reply to @{screen_name} ({int(age / 60)} min ago)")
                    return True
    except Exception as e:
        print(f"❌ Error checking recent replies: {e}")
    return False

# Fetch mentions and populate queue
def respond_to_mentions(client_v2, client_v1):
    recipients = load_json_set(RECIPIENTS_FILE)
    failed = load_json_set(FAILED_FILE)
    state = load_state()
    last_seen_id = state.get("last_seen_id")
    queue = load_queue()

    try:
        print("🔍 Searching for new mentions...")
        query = "@nobodypfp create a PFP for me"
        response = client_v2.search_recent_tweets(
            query=query,
            since_id=last_seen_id,
            max_results=10,
            tweet_fields=["author_id"]
        )
        print("✅ Found tweets:", response.data)
    except Exception as e:
        print("❌ Error searching tweets:", e)
        return

    if not response.data:
        print("ℹ️ No new tweets found.")
        return

    new_last_seen_id = last_seen_id
    queued_ids = {item['tweet_id'] for item in queue}

    for tweet in reversed(response.data):
        print(f"📨 Processing tweet ID {tweet.id} with text: {tweet.text}")
        text = tweet.text.lower()
        author_id = tweet.author_id
        tweet_id = tweet.id

        if new_last_seen_id is None or tweet_id > new_last_seen_id:
            new_last_seen_id = tweet_id

        if "create a pfp for me" not in text:
            print("⏭ Skipping - does not contain trigger phrase.")
            continue

        try:
            print("📌 Getting user info for author:", author_id)
            user_obj = client_v2.get_user(id=author_id)
            screen_name = user_obj.data.username.lower()
            print("✅ Got user:", screen_name)
        except Exception as e:
            print("❌ Error fetching user info:", e)
            continue

        if tweet_id in queued_ids or screen_name in recipients or screen_name in failed:
            print(f"⚠️ Skipping @{screen_name} (already queued, served, or failed).")
            continue

        if has_recent_reply(client_v1, screen_name):
            print(f"⚠️ @{screen_name} was replied to recently. Skipping.")
            continue

        queue.append({
            "tweet_id": tweet_id,
            "author_id": author_id,
            "screen_name": screen_name
        })

    if new_last_seen_id:
        state["last_seen_id"] = new_last_seen_id
        save_state(state)

    save_queue(queue)

# Serve replies from queue
def serve_from_queue(client_v1):
    queue = load_queue()
    used_images = load_json_set(USED_IMAGES_FILE)
    recipients = load_json_set(RECIPIENTS_FILE)
    failed = load_json_set(FAILED_FILE)

    print(f"📋 Queue length: {len(queue)}")

    if not queue:
        print("ℹ️ No users in queue.")
        return

    current = queue.pop(0)
    tweet_id = current["tweet_id"]
    screen_name = current["screen_name"]

    if screen_name in recipients or screen_name in failed:
        print(f"⚠️ @{screen_name} already handled. Skipping.")
        save_queue(queue)
        return

    image_file = get_unused_image(used_images)
    if not image_file:
        print("⚠️ No more unused images.")
        return

    image_path = download_image(image_file)
    if not image_path:
        print("❌ Failed to download image. Skipping.")
        failed.add(screen_name)
        save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return

    try:
        print("📤 Uploading image...")
        media = client_v1.media_upload(image_path)
        print("✅ Uploaded media")
    except Exception as e:
        print("❌ Error uploading media:", e)
        failed.add(screen_name)
        save_json_set(failed, FAILED_FILE)
        save_queue(queue)
        return
    finally:
        if os.path.exists(TEMP_IMAGE_FILE):
            os.remove(TEMP_IMAGE_FILE)

    try:
        print("📢 Posting reply tweet...")

        responses = [
            "Here's your Nobody PFP 👁️ @{screen_name}",
            "Your custom Nobody PFP is ready 👁️ @{screen_name}",
            "All yours 👁️ @{screen_name}",
            "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
            "Cooked just for you 👁️ @{screen_name}",
            "Made with nothingness 👁️ @{screen_name}",
            "👁️ For the void... and @{screen_name}",
        ]
        status_text = random.choice(responses).replace("{screen_name}", screen_name)

        client_v1.update_status(
            status=status_text,
            in_reply_to_status_id=tweet_id,
            auto_populate_reply_metadata=True,
            media_ids=[media.media_id]
        )
        print(f"🎉 Sent PFP {image_file} to @{screen_name}")
    except Exception as e:
        print("❌ Error posting tweet:", e)
        failed.add(screen_name)
        save_json_set(failed, FAILED_FILE)

        if "429" in str(e):
            print("🚫 Rate limit hit — sleeping for 60 seconds.")
            time.sleep(60)

        save_queue(queue)
        return

    used_images.add(image_file)
    recipients.add(screen_name)
    save_json_set(used_images, USED_IMAGES_FILE)
    save_json_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)

    time.sleep(10)
