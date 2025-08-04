import os
import json
import random
import time

# ─── CONFIG ──────────────────────────────────────────────────────────────
USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
FAILED_FILE        = "/data/failed.json"
QUEUE_FILE         = "/data/queue.json"

B2_IMAGE_BASE_URL  = "https://f004.backblazeb2.com/file/NobodyPFPs/"

# ─── HELPERS ─────────────────────────────────────────────────────────────
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

def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, "r") as f:
            return json.load(f)
    return []

def save_queue(queue):
    with open(QUEUE_FILE, "w") as f:
        json.dump(queue, f)

# ─── IMAGE SELECTION ──────────────────────────────────────────────────────
def get_unused_image(used_images):
    all_images = [f"{i}.png" for i in range(10000)]
    available  = list(set(all_images) - used_images)
    return random.choice(available) if available else None

# ─── FETCH MENTIONS → ENQUEUE ────────────────────────────────────────────
def respond_to_mentions(client_v2):
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
        print(f"❌ Error searching tweets: {e}")
        return

    new_last = last_seen_id
    queued_ids = {job["tweet_id"] for job in queue}

    for tw in reversed(tweets):
        tid = tw.id
        if not new_last or tid > new_last:
            new_last = tid

        text = tw.text.lower()
        if "create a pfp for me" not in text:
            continue

        try:
            usr = client_v2.get_user(id=tw.author_id).data.username.lower()
        except Exception as e:
            print(f"❌ Error fetching user: {e}")
            continue

        if tid in queued_ids or usr in recipients or usr in failed:
            continue

        queue.append({"tweet_id": tid, "screen_name": usr})
        print(f"➕ Queued @{usr} (tweet {tid})")

    if new_last:
        state["last_seen_id"] = new_last
        save_state(state)
    save_queue(queue)

# ─── SERVE QUEUE → DRIP REPLIES ─────────────────────────────────────────
def serve_from_queue(client_v2):
    queue      = load_queue()
    if not queue:
        print("ℹ️ Queue empty.")
        return

    used_images = load_json_set(USED_IMAGES_FILE)
    recipients  = load_json_set(RECIPIENTS_FILE)
    failed      = load_json_set(FAILED_FILE)

    job = queue.pop(0)
    tid = job["tweet_id"]
    usr = job["screen_name"]

    # skip if already done
    if usr in recipients or usr in failed:
        save_queue(queue)
        return

    img = get_unused_image(used_images)
    if not img:
        print("⚠️ No unused images left.")
        return

    # craft reply with embedded URL
    image_url = B2_IMAGE_BASE_URL + img
    templates = [
        "Here's your Nobody PFP 👁️ @{screen_name}",
        "Your custom Nobody PFP is ready 👁️ @{screen_name}",
        "All yours 👁️ @{screen_name}",
        "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
        "Cooked just for you 👁️ @{screen_name}",
        "Made with nothingness 👁️ @{screen_name}",
        "👁️ For the void... and @{screen_name}",
    ]
    text = random.choice(templates).format(screen_name=usr) + " " + image_url

    try:
        print(f"📢 Replying to @{usr} (tweet {tid}) with link…")
        client_v2.create_tweet(
            text=text,
            in_reply_to_tweet_id=tid
        )
        print(f"🎉 Sent link to @{usr}")
    except Exception as e:
        print(f"❌ Reply failed: {e}")
        failed.add(usr)
        save_json_set(failed, FAILED_FILE)
        # we could re-queue on rate limit, but v2 only should rarely hit it
        queue.insert(0, job)
        save_queue(queue)
        return

    # record success
    used_images.add(img)
    recipients.add(usr)
    save_json_set(used_images, USED_IMAGES_FILE)
    save_json_set(recipients, RECIPIENTS_FILE)
    save_queue(queue)

    # throttle
    time.sleep(10)
