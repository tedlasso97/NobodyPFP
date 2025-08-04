import os
import json
import random
import time
import requests
from auth import get_twitter_conn_v1

# ───── CONFIG ────────────────────────────────────────────────────────────
USED_IMAGES_FILE   = "/data/used_images.json"
RECIPIENTS_FILE    = "/data/recipients.json"
STATE_FILE         = "/data/state.json"
IMAGES_DIR         = "images"   # your local folder of 0–9999.png
B2_BASE_URL        = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_FILE          = "temp.png"

REPLY_TEMPLATES = [
    "Here's your Nobody PFP 👁️ @{screen_name}",
    "Your custom Nobody PFP is ready 👁️ @{screen_name}",
    "All yours 👁️ @{screen_name}",
    "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
    "Cooked just for you 👁️ @{screen_name}",
    "Made with nothingness 👁️ @{screen_name}",
    "👁️ For the void... and @{screen_name}",
]

# ───── LOW-LEVEL HELPERS ───────────────────────────────────────────────────
def _load(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def _save(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f)

def load_state():
    return _load(STATE_FILE, {"last_seen_id": None})

def save_state(s):
    _save(s, STATE_FILE)

def load_set(path):
    return set(_load(path, []))

def save_set(s, path):
    _save(list(s), path)

# ───── IMAGE FUNCTIONS ─────────────────────────────────────────────────────
def pick_image(used):
    all_imgs = os.listdir(IMAGES_DIR)
    avail    = list(set(all_imgs) - used)
    return random.choice(avail) if avail else None

def download_img(fn):
    url = f"{B2_BASE_URL}{fn}"
    r   = requests.get(url); r.raise_for_status()
    with open(TEMP_FILE, "wb") as f:
        f.write(r.content)
    return TEMP_FILE

# ───── BOOTSTRAP EXISTING REPLIES ──────────────────────────────────────────
def bootstrap_recipients(client_v2):
    """Scan your bot’s own recent tweets for replies and seed recipients.json."""
    recipients = load_set(RECIPIENTS_FILE)
    try:
        me = client_v2.get_me().data
        resp = client_v2.get_users_tweets(
            me.id,
            max_results=100,
            tweet_fields=["in_reply_to_user_id"]
        )
        for tw in resp.data or []:
            rid = tw.in_reply_to_user_id
            if rid:
                user = client_v2.get_user(id=rid).data.username.lower()
                recipients.add(user)
    except Exception as e:
        print("❌ bootstrap error:", e)
    save_set(recipients, RECIPIENTS_FILE)
    return recipients

# ───── MAIN PASS ───────────────────────────────────────────────────────────
def run_once(client_v2):
    v1         = get_twitter_conn_v1()
    state      = load_state()
    last_seen  = state.get("last_seen_id")

    used_imgs  = load_set(USED_IMAGES_FILE)
    # merge in any manual or prior replies
    recipients = bootstrap_recipients(client_v2)
    new_last   = last_seen

    # 1) Fetch
    resp = client_v2.search_recent_tweets(
        query="@nobodypfp create a PFP for me -is:retweet",
        since_id=last_seen,
        max_results=50,
        tweet_fields=["author_id"]
    )
    tweets = resp.data or []

    for tw in reversed(tweets):
        tid = tw.id
        if not new_last or tid > new_last:
            new_last = tid

        if "create a pfp for me" not in tw.text.lower():
            continue

        user = client_v2.get_user(id=tw.author_id).data.username.lower()
        if user in recipients:
            continue

        # 2) Pick & download image
        img = pick_image(used_imgs)
        if not img:
            print("⚠️ Out of images.")
            break
        path = download_img(img)

        # 3) Upload & reply via v1.1
        try:
            m = v1.media_upload(path)
            txt = random.choice(REPLY_TEMPLATES).format(screen_name=user)
            v1.update_status(
                status=txt,
                in_reply_to_status_id=tid,
                auto_populate_reply_metadata=True,
                media_ids=[m.media_id_string]
            )
            print(f"🎉 replied to @{user}")
        except Exception as e:
            print(f"❌ failed to reply @{user}:", e)
            break  # on rate-limit or forbidden, stop this run

        # 4) Record success
        used_imgs.add(img)
        recipients.add(user)
        save_set(used_imgs, USED_IMAGES_FILE)
        save_set(recipients, RECIPIENTS_FILE)

        time.sleep(2)  # small throttle

    # 5) Persist new cursor
    if new_last and new_last != last_seen:
        save_state({"last_seen_id": new_last})
