import os
import json
import random
import requests
from auth import get_twitter_conn_v1

# Use persistent storage
USED_IMAGES_FILE = "/data/used_images.json"
RECIPIENTS_FILE = "/data/recipients.json"
STATE_FILE = "/data/state.json"

B2_IMAGE_BASE_URL = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_IMAGE_FILE = "temp_image.png"

def load_used_images():
    if os.path.exists(USED_IMAGES_FILE):
        with open(USED_IMAGES_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_used_images(used):
    with open(USED_IMAGES_FILE, "w") as f:
        json.dump(list(used), f)

def load_recipients():
    if os.path.exists(RECIPIENTS_FILE):
        with open(RECIPIENTS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_recipients(recipients):
    with open(RECIPIENTS_FILE, "w") as f:
        json.dump(list(recipients), f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_seen_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

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

def respond_to_mentions(client_v2):
    used_images = load_used_images()
    recipients = load_recipients()
    state = load_state()
    last_seen_id = state.get("last_seen_id")

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

    for tweet in reversed(response.data):  # Oldest first
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

        if screen_name in recipients:
            print(f"⚠️ {screen_name} already got a PFP.")
            try:
                client_v2.create_tweet(
                    text=f"You already received a Nobody PFP @{screen_name}",
                    in_reply_to_tweet_id=tweet_id
                )
            except Exception as e:
                print("❌ Error sending duplicate notification:", e)
            continue

        image_file = get_unused_image(used_images)
        if not image_file:
            print("⚠️ No more unused images.")
            return

        image_path = download_image(image_file)
        if not image_path:
            print("❌ Failed to download image. Skipping.")
            continue

        try:
            print("📤 Uploading image...")
            client_v1 = get_twitter_conn_v1()
            media = client_v1.media_upload(image_path)
            print("✅ Uploaded media")
        except Exception as e:
            print("❌ Error uploading media:", e)
            continue
        finally:
            if os.path.exists(TEMP_IMAGE_FILE):
                os.remove(TEMP_IMAGE_FILE)

        try:
            print("📢 Posting reply tweet...")
            client_v2.create_tweet(
                text=f"Here is your Nobody PFP @{screen_name}",
                in_reply_to_tweet_id=tweet_id,
                media_ids=[media.media_id]
            )
            print(f"🎉 Sent PFP {image_file} to @{screen_name}")
        except Exception as e:
            print("❌ Error posting tweet:", e)
            continue

        used_images.add(image_file)
        recipients.add(screen_name)
        save_used_images(used_images)
        save_recipients(recipients)

    if new_last_seen_id:
        state["last_seen_id"] = new_last_seen_id
        save_state(state)
